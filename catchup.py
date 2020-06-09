import subprocess
import parameters
import sys
import time
import random
import os
import json

#-------------------------------#
#	Global Variables
#-------------------------------#
version="1.0.0"
ns=""
divider="--------------------------------------"

#-------------------------------#
#	Functions
#-------------------------------#

#--------------------
#	Check if the specified NameSpace already exists with the K8S cluster
#--------------------
def check_ns():
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

	if detected:
		print(divider)
		print("Removing legacy namespace[{}]. This may take a few seconds...".format(ns))
		execute_command("kubectl delete ns {}".format(ns))
		execute_command("kubectl delete clusterrolebinding couchbase-operator-admission-{0}".format(ns))
		execute_command("kubectl delete mutatingwebhookconfiguration couchbase-operator-admission-{0}".format(ns))
		execute_command("kubectl delete validatingwebhookconfiguration couchbase-operator-admission-{0}".format(ns))

	return ns


#--------------------
#	Wrapper method to execute an arbitrary command
#--------------------
def execute_command(command):
	print(divider)
	print("Executing command : {}".format(command))
	p=subprocess.Popen(command, shell=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
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
	tmppod="undefined"
	p = subprocess.Popen("kubectl get pods -n {}".format(ns), shell=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
	for line in p.stdout.readlines():
		spaces = line.split()
		if prefix in spaces[0].decode("ascii") and spaces[1].decode("ascii") == "1/1":
			tmppod=spaces[0].decode("ascii")
			break

	if tmppod != "undefined":
		p2 = subprocess.Popen("kubectl exec -it {0} -n {1} -- curl --user \"Administrator:password\" --silent \"http://localhost:8091/pools/default/nodeServices\"".format(
			tmppod, ns), shell=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
		for line in p2.stdout.readlines():
			svcmap=line.decode("ascii")

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
	p = subprocess.Popen("kubectl exec -it {0} -n {1} -- curl -u \"Administrator:password\" http://localhost:8091/pools".format(podname, ns), shell=True, stdout=subprocess.PIPE,
						 stderr=subprocess.STDOUT)
	for line in p.stdout.readlines():
		clusterstring = line.decode("ascii")

	tmpmap = json.loads(clusterstring)

	return tmpmap["uuid"]


def configure_xdcr():
	orig_pod = get_pod_by_svc("cb-example-0", ns, "kv").split(".")[0]
	xdcr_pod = get_pod_by_svc("cb-example-xdcr", ns, "kv").split(".")[0]
	xdcr_uuid = execute_command()


def stop_portforward():
	p = subprocess.Popen("ps -ef | grep port-forward | grep -v grep", shell=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
	count = 0
	for line in p.stdout.readlines():
		print("{} - {}".format(count, line.decode("ascii")))
		count += 1


def display_menu():
	print("")
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
			if x >= 1 and x <= 4:
				run = False
			else:
				print("Invalid selection.  Please select a number between 1 and 4")
		except ValueError:
			print("Invalid selection.  Please select a number between 1 and 4")

	return selection



#-------------------------------#
#	Main Program
#-------------------------------#
if __name__ == "__main__":
	#svcpod = get_pod_by_svc("cb-example", "test2", "kvv")
	selection = display_menu()
	#stop_portforward()
	#sys.exit(0)
	ns = check_ns()

	if selection >=1:
		print(divider)
		print("(Re)building your namespace. This may take a few seconds...")
		execute_command("python eks_script.py -n {}".format(ns))

	if selection >= 2:
		execute_command("kubectl create -f resources/couchbase-cluster.yaml --save-config -n {}".format(ns))
		execute_command("kubectl create -f resources/solutions/exercise_1/couchbase-cluster2.yaml --save-config -n {}".format(ns))
		print("Waiting for clusters to be ready")
		ready = wait_till_ready("cb-example-0", 3, ns, 30, 10)
		ready = ready & wait_till_ready("cb-example-xdcr", 2, ns, 30, 10)
		print("Clusters detected as ready")
		execute_background_command("nohup kubectl port-forward {0} 8091:8091 -n {1}".format(
			get_pod_by_svc("cb-example-0", ns, "kv").split(".")[0], ns
		))

		execute_background_command("nohup kubectl port-forward {0} 8092:8091 -n {1}".format(
			get_pod_by_svc("cb-example-xdcr", ns, "kv").split(".")[0], ns
		))

		print(get_uuid("cb-example-xdcr-0000", "test2"))

	if selection >= 3:
		print("TODO - Add pre-steps for exercise three")

	if selection >= 4:
		print("TODO - Run all steps until completion")
