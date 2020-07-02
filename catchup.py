import subprocess
import parameters
import sys
import time
import random
import os
import json

# -------------------------------#
# Global Variables
# -------------------------------#
version = "1.0.0"
ns = ""
divider = "--------------------------------------"


# -------------------------------#
# Functions
# -------------------------------#

# --------------------
# Check if the specified NameSpace already exists with the K8S cluster
# --------------------
def check_ns(delete):
    if sys.version_info[0] < 3:
        ns = raw_input("Enter a namespace : ")
    else:
        ns = input("Enter a namespace : ")
    print("Checking ns[{}]".format(ns))

    detected = False
    p = subprocess.Popen("kubectl get ns", shell=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    for line in p.stdout.readlines():
        spaces = line.split()
        if spaces[0].decode('ascii') == ns:
            detected = True
    retval = p.wait()

    if detected and delete:
        print(divider)
        print("Removing legacy namespace[{}]. This may take a few seconds...".format(ns))
        execute_command("kubectl delete ns {}".format(ns))
        execute_command("kubectl delete clusterrolebinding couchbase-operator-admission-{0}".format(ns))
        execute_command("kubectl delete mutatingwebhookconfiguration couchbase-operator-admission-{0}".format(ns))
        execute_command("kubectl delete validatingwebhookconfiguration couchbase-operator-admission-{0}".format(ns))

    return ns


# --------------------
# Wrapper method to execute an arbitrary command
# --------------------
def execute_command(command):
    print(divider)
    print("Executing command : {}".format(command))
    p = subprocess.Popen(command, shell=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    for line in p.stdout.readlines():
        print(line)
    retval = p.wait()

    if retval != 0:
        print ("Error encountered running command: {}".format(command))
        sys.exit(retval)


def execute_background_command(command):
    print(divider)
    print("Executing command : {}".format(command))
    p = subprocess.Popen(command, shell=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)


def get_pod_by_svc(prefix, ns, svc):
    tmppod = "undefined"
    svcmap = "undefined"
    p = subprocess.Popen("kubectl get pods -n {}".format(ns), shell=True, stdout=subprocess.PIPE,
                         stderr=subprocess.STDOUT)
    for line in p.stdout.readlines():
        spaces = line.split()
        if len(spaces) >= 2:
            if prefix in spaces[0].decode("ascii") and spaces[1].decode("ascii") == "1/1":
                tmppod = spaces[0].decode("ascii")
                break

    if tmppod != "undefined":
        p2 = subprocess.Popen(
            "kubectl exec -it {0} -n {1} -- curl --user \"Administrator:password\" --silent \"http://localhost:8091/pools/default/nodeServices\"".format(
                tmppod, ns), shell=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        for line in p2.stdout.readlines():
            svcmap = line.decode("ascii")

    if svcmap != "undefined":
        parsedmap = json.loads(svcmap)
        for i in parsedmap["nodesExt"]:
            for j in i["services"]:
                if j == svc:
                    return i["hostname"]

    return "undefined"


def wait_till_ready(prefix, cnt, ns, sleep, maxtries):
    attempt = 1
    passed = False
    while attempt <= maxtries and not passed:
        print("Checking availability of cluster[{0}]. Attempt: {1}".format(prefix, attempt))
        count = 0
        p = subprocess.Popen("kubectl get pods -n {}".format(ns), shell=True, stdout=subprocess.PIPE,
                             stderr=subprocess.STDOUT)
        for line in p.stdout.readlines():
            spaces = line.split()
            if prefix in spaces[0].decode("ascii") and spaces[1].decode("ascii") == "1/1":
                count = count + 1

        if count == cnt:
            passed = True
        else:
            attempt = attempt + 1
            time.sleep(sleep)

    return passed


def get_uuid(podname, ns):
    p = subprocess.Popen(
        "kubectl exec -it {0} -n {1} -- curl -u \"Administrator:password\" http://localhost:8091/pools".format(podname,
                                                                                                               ns),
        shell=True, stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT)
    for line in p.stdout.readlines():
        clusterstring = line.decode("ascii")

    tmpmap = json.loads(clusterstring)

    return tmpmap["uuid"]


def configure_xdcr(ns):
    orig_pod = get_pod_by_svc("cb-example-0", ns, "kv").split(".")[0]
    xdcr_pod = get_pod_by_svc("cb-example-xdcr", ns, "kv").split(".")[0]
    xdcr_pod_full = get_pod_by_svc("cb-example-xdcr", ns, "kv")
    remote_uuid = get_uuid(xdcr_pod, ns)

    cmd = "kubectl exec -it {0} -n {1} -- curl -v -u \"Administrator:password\" --silent http://localhost:8091/pools/default/remoteClusters -d {2} -d {3} -d {4} -d {5} -d {6}"
    execute_command(cmd.format(orig_pod, ns, "uuid={}".format(remote_uuid), "name=my-xdcr-cluster",
                               "hostname={}:8091".format(xdcr_pod_full), "username=Administrator",
                               "password=password"))

    cmdprefix = "kubectl exec -it {0} -n {1} --".format(orig_pod, ns)
    replicationcmd = "{0} curl -v -u \"Administrator:password\" --silent http://localhost:8091/controller/createReplication -d {1} -d {2} -d {3} -d {4} -d {5}"
    execute_command(replicationcmd.format(cmdprefix, "fromBucket=couchmart", "toCluster=my-xdcr-cluster",
                                          "toBucket=couchmart", "replicationType=continuous",
                                          "compressionType=Auto"))

    return remote_uuid


def stop_portforward():
    if sys.platform.startswith('freebsd') or sys.platform.startswith('linux') or sys.platform.startswith(
            'aix') or sys.platform.startswith('darwin'):
        cmd = "ps -ef | grep kubectl | grep -v grep | tr -s ' ' | cut -d' ' -f3"
        stopcmd = "kill -9 {0}"
    elif sys.platform.startswith('win32') or sys.platform.startswith('cygwin'):
        cmd = "powershell Get-Process | grep kubectl | grep -v grep | tr -s ' '| cut -d' ' -f7"
        stopcmd = "powershell Stop-Process {0}"
    else:
        cmd = "ps -ef | grep kubectl | grep -v grep | tr -s ' ' | cut -d' ' -f3"
        stopcmd = "kill -9 {0}"

    p = subprocess.Popen(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    for line in p.stdout.readlines():
        execute_command(stopcmd.format(line))


def start_portforward():
    if sys.platform.startswith('freebsd') or sys.platform.startswith('linux') or sys.platform.startswith(
            'aix') or sys.platform.startswith('darwin'):
        cmd = "nohup kubectl port-forward {0} {2}:{3} -n {1} > /dev/null 2>&1 &"
    elif sys.platform.startswith('win32') or sys.platform.startswith('cygwin'):
        cmd = "invoke-expression 'cmd /c start /min powershell -Command { kubectl port-forward {0} {2}:{3} -n {1} }'"
        #cmd = "kubectl port-forward {0} {2}:{3} -n {1}"
    else:
        cmd = "nohup kubectl port-forward {0} {2}:{3} -n {1} > /dev/null 2>&1 &"

    pod = get_pod_by_svc("cb-example-0", ns, "kv").split(".")[0]
    if pod != "undefined":
        execute_background_command(cmd.format(
            pod, ns, "8091", "8091"
        ))

    pod = get_pod_by_svc("cb-example-xdcr", ns, "kv").split(".")[0]
    if pod != "undefined":
        execute_background_command(cmd.format(
            pod, ns, "8092", "8091"
        ))

    pod = get_pod_name_by_prefix("couchmart", ns)
    if pod != "undefined":
        execute_background_command(cmd.format(
            pod, ns, "8080", "8080"
        ))


def get_pod_name_by_prefix(prefix, ns):
    p = subprocess.Popen("kubectl get pods -n {}".format(ns), shell=True, stdout=subprocess.PIPE,
                         stderr=subprocess.STDOUT)
    for line in p.stdout.readlines():
        spaces = line.split()
        if len(spaces) >= 2:
            if prefix in spaces[0].decode("ascii") and spaces[1].decode("ascii") == "1/1":
                return spaces[0].decode("ascii")

    return "undefined"


def setup_couchmart(ns):
    cmpod = get_pod_name_by_prefix("couchmart", ns)
    if cmpod != "undefined":
        execute_command(
            "kubectl exec -it {0} -n {1} -- bash -c \"cd /couchmart && git clean -fdx && git checkout -f couchbasesummit\"".format(
                cmpod, ns))
        execute_command(
            "kubectl exec -i {0} -n {1} -- bash -c \"cd /scripts && ./restart_couchmart.sh\"".format(cmpod, ns))


def update_couchmart(ns, webfile):
    cmpod = get_pod_name_by_prefix("couchmart", ns)
    if cmpod != "undefined":
        execute_command(
            "kubectl exec -it {0} -n {1} -- bash -c \"cp /couchmart/web-server.py /couchmart/web-server.py.bkup\"".format(
                cmpod, ns
            ))
        execute_command("kubectl exec -it {0} -n {1} -- bash -c \"cp /solutions/{2} /couchmart/web-server.py\"".format(
            cmpod, ns, webfile
        ))

        execute_command(
            "kubectl exec -it {0} -n {1} -- sed -e \"s/<Couchbase node>/{2}/g\" -i.bkup /couchmart/web-server.py".format(
                cmpod, ns, get_pod_by_svc("cb-example-0", ns, "kv")
            ))

        execute_command(
            "kubectl exec -i {0} -n {1} -- bash -c \"cd /scripts && ./restart_couchmart.sh\"".format(cmpod, ns))


def print_close():
    print("")
    print(divider)
    print("You are all caught up.  Please leave this window open")
    print(divider)


def display_menu():
    print("")
    print("")
    print("Optional functionality:")
    print("")
    print("	0 - Restart all port-forwarding")
    print("")
    print("Please select the exercise you want to jump to:")
    print("")
    print("	1 - Exercise 1 : XDCR, Python SDK connection, Python SDK KV Read, Python SDK KV Write")
    print("	2 - Exercise 2 : Index, N1QL, FTS")
    print("	3 - Exercise 3 : Analytics, Eventing")
    print("	4 - Final : The completed exercise")
    print("")
    selection = 0
    run = True
    while run:
        if sys.version_info[0] < 3:
            selection = raw_input("Enter selection : ")
        else:
            selection = input("Enter selection : ")

        try:
            x = int(selection)
            if x >= 0 and x <= 4:
                run = False
            else:
                print("Invalid selection.  Please select a number between 0 and 4")
        except ValueError:
            print("Invalid selection.  Please select a number between 0 and 4")

    return selection


# -------------------------------#
# Main Program
# -------------------------------#
if __name__ == "__main__":
    # svcpod = get_pod_by_svc("cb-example", "test2", "kvv")
    waittime=30
    waitattempts=10

    selection = int(display_menu())
    if selection == 0:
        ns = check_ns(False)
        stop_portforward()
        start_portforward()
        print_close()
        sys.exit(0)

    print(divider)
    print("Stopping any existing port-forward commands. These will be recreated as part of the catchup process...")
    print(divider)
    stop_portforward()
    ns = check_ns(True)

    if selection >= 1:
        print(divider)
        print("(Re)building your namespace. This may take a few seconds...")
        execute_command("python eks_script.py -n {}".format(ns))

        # Couchbase Cluster
        execute_command("kubectl create -f resources/solutions/exercise_1/couchbase-cluster.yaml --save-config -n {}".format(ns))
        print("Waiting for cluster to be ready")
        ready = wait_till_ready("cb-example-0", 3, ns, waittime, waitattempts)
        if not ready:
            print("Cluster is not detected as ready, exiting...")
            sys.exit(1)
        else:
            print("Clusters detected as ready")

        # Couchmart
        cmpod = get_pod_name_by_prefix("couchmart", ns)
        execute_command("kubectl exec -it {0} -n {1} -- python /couchmart/create_dataset.py".format(cmpod, ns))

    if selection >= 2:
        # Couchbase Clusters - XDCR
        execute_command(
            "kubectl create -f resources/solutions/exercise_1/couchbase-cluster2.yaml --save-config -n {}".format(ns))

        print("Waiting for clusters to be ready")
        ready = wait_till_ready("cb-example-xdcr", 2, ns, waittime, waitattempts)
        if not ready:
            print("Cluster is not detected as ready, exiting...")
            sys.exit(1)
        else:
            print("Clusters detected as ready")

        # XDCR
        xdcr_uuid = configure_xdcr(ns)

        # Couchmart - Connection, KV read and KV write
        setup_couchmart(ns)
        update_couchmart(ns, "web-server-exercise1.py")

    if selection >= 3:
        # Update Couchbase Cluster with new pods
        execute_command(
            "kubectl apply -f resources/solutions/exercise_2/couchbase-cluster.yaml -n {}".format(ns))

        print("Waiting for clusters to be ready")
        ready = ready & wait_till_ready("cb-example-0", 7, ns, waittime, waitattempts)
        if not ready:
            print("Cluster is not detected as ready, exiting...")
            sys.exit(1)
        else:
            print("Clusters detected as ready")

        # Create index
        querypod = get_pod_by_svc("cb-example-0", ns, "n1ql").split(".")[0]
        if querypod != "undefined":
            execute_command(
                "kubectl exec -it {0} -n {1} -- bash -c \"cbq -e couchbase://localhost -u Administrator -p password -s {2}\"".format(
                    querypod, ns, "\'CREATE INDEX idx_category ON couchmart(category)\'"
                ))

        # Create FTS index
        ftspod = get_pod_by_svc("cb-example-0", ns, "fts").split(".")[0]
        if ftspod != "undefined":
            execute_command(
                "kubectl cp resources/solutions/exercise_2/fts_English.json {0}/{1}:/fts_English.json".format(
                    ns, ftspod
                ))

            ftscommand = "curl -u Administrator:password -XPUT {0}" \
                         " -H \"cache-control: no-cache\"" \
                         " -H \"content-type: application/json\"" \
                         " -d @/fts_English.json"

            execute_command("kubectl exec -it {0} -n {1} -- {2}".format(ftspod, ns,
                                                                        ftscommand.format(
                                                                            "http://localhost:8094/api/index/English")))
        #Update couchmart
        update_couchmart(ns, "web-server-exercise2.py")

    if selection >= 4:

        #Data update
        if querypod != "undefined":
            execute_command(
                "kubectl exec -it {0} -n {1} -- bash -c \"cbq -e couchbase://localhost -u Administrator -p password -s {2}\"".format(
                    querypod, ns, "\'CREATE INDEX couchmart_product_idx ON couchmart(type) WHERE type = \"product\"\'"
                ))

            execute_command(
                "kubectl exec -it {0} -n {1} -- bash -c \"cbq -e couchbase://localhost -u Administrator -p password -s {2}\"".format(
                    querypod, ns, "\'UPDATE couchmart set cost=price * 0.8 WHERE type = \"product\"\'"
                ))

        kvpod = get_pod_by_svc("cb-example-0", ns, "kv").split(".")[0]
        if kvpod != "undefined":
            execute_command("kubectl exec -it {0} -n {1} -- curl -u Administrator:password -XPOST"
                            " http://localhost:8091/settings/replications/{2}%2Fcouchmart%2Fcouchmart"
                            " -d pauseRequested=true".format(kvpod, ns, xdcr_uuid))

            execute_command("kubectl exec -i {0} -n {1} -- bash -c \"wget http://bit.ly/cbsummitdata1M -O /tmp/couchmart_1M_formatted_keys.json\"".format(
                kvpod, ns
            ))

            execute_command("kubectl exec -i {0} -n {1} -- cbimport json -c couchbase://localhost "
                            "-b couchmart -u Administrator -p password -f list "
                            "-d file:///tmp/couchmart_1M_formatted_keys.json -g %_id%".format(
                kvpod, ns
            ))

        #Analytics
        cbaspod = get_pod_by_svc("cb-example-0", ns, "cbas").split(".")[0]
        if cbaspod != "undefined":
            execute_command(
                "kubectl cp resources/solutions/exercise_3/analytic_queries.txt {0}/{1}:/analytic_queries.txt".format(
                    ns, cbaspod
                ))

            execute_command(
                "kubectl exec -it {0} -n {1} -- bash -c \"cbq -e http://localhost:8095 -u Administrator -p password -f=\"/analytic_queries.txt\"\"".format(
                    cbaspod, ns
                ))

        #Eventing
        if querypod != "undefined":
            execute_command(
                "kubectl exec -it {0} -n {1} -- bash -c \"cbq -e couchbase://localhost -u Administrator -p password -s {2}\"".format(
                    querypod, ns, "\'CREATE PRIMARY INDEX ON fulfillment\'"
                ))

        eventingpod = get_pod_by_svc("cb-example-0", ns, "eventingAdminPort").split(".")[0]
        if eventingpod != "undefined":
            execute_command(
                "kubectl cp resources/solutions/exercise_3/manage_orders.json {0}/{1}:/manage_orders.json".format(
                    ns, eventingpod
                ))
            cmd = "curl -u Administrator:password -XPOST {0}" \
                  " -H \"cache-control: no-cache\"" \
                  " -H \"content-type: application/json\"" \
                  " -d @/manage_orders.json"
            execute_command("kubectl exec -it {0} -n {1} -- {2}".format(
                        eventingpod, ns, cmd.format("http://localhost:8096/api/v1/functions/manage_orders")
                    ))

            execute_command(
                "kubectl cp resources/solutions/exercise_3/deploy_eventing.json {0}/{1}:/deploy_eventing.json".format(
                    ns, eventingpod
                ))
            cmd = "curl -u Administrator:password -XPOST {0}" \
                  " -H \"cache-control: no-cache\"" \
                  " -H \"content-type: application/json\"" \
                  " -d @/deploy_eventing.json"
            execute_command("kubectl exec -it {0} -n {1} -- {2}".format(
                eventingpod, ns, cmd.format("http://localhost:8096/api/v1/functions/manage_orders/settings")
            ))

    # Shared commands
    start_portforward()
    print_close()
