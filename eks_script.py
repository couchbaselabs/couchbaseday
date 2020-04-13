import subprocess
import parameters
import sys
import time
import random
import os

#-------------------------------#
#	Global Variables
#-------------------------------#
version="1.1.0"
ns=""
divider="--------------------------------------"
se_user=False
create_cluster=False
create_couchmart=True

#-------------------------------#
#	Functions
#-------------------------------#

#--------------------
#	Check if the specified NameSpace already exists with the K8S cluster
#--------------------
def check_ns():
	print("Running eks deployment script")
	if sys.version_info[0] < 3:
		ns = raw_input("Enter a namespace : ")
	else:
		ns = input("Enter a namespace : ")
	print("Checking ns[{}]".format(ns))

	for x in range(parameters.NS_ATTEMPTS):
		print("Checking attempt #{}".format(x))
		p=subprocess.Popen("{} get ns".format(COMMAND), shell=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
		for line in p.stdout.readlines():
			spaces=line.split()
			if spaces[0].decode('ascii') == ns:
				return ""
		retval = p.wait()
		time.sleep(random.randint(1,parameters.NS_WAIT_VARIANCE))
		

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

#--------------------
#	Create the namespace yaml in the resources folder
#--------------------
def create_namespace_yaml():
	f = open("./resources/namespace.yaml","w")
	f.write("kind: Namespace\n")
	f.write("apiVersion: v1\n")
	f.write("metadata:\n")
	f.write("  name: {0}\n".format(ns))
	f.write("  labels:\n")
	f.write("    name: {0}\n".format(ns))
	f.close()

#--------------------
#	Check the Couchmart deployment status
#--------------------
def check_status(ns):
	print(divider)

	retVal=False
	maxTry=parameters.CM_RETRY_ATTEMPTS
	myTry=1

	while retVal == False and myTry <= maxTry:
		print ("Checking couchmart pod status : attempt {}".format(myTry))
		myTry = myTry + 1
		p=subprocess.Popen("{0} get pods --namespace {1}".format(COMMAND,ns), shell=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
		for line in p.stdout.readlines():
			spaces=line.split()
			if "couchmart" in spaces[0].decode('ascii') and "deploy" not in spaces[0].decode('ascii'):
				if spaces[1].decode('ascii') == "1/1":
					print(spaces[0].decode('ascii') + "  " + spaces[1].decode('ascii'))
					retVal=True
				else:
					print(spaces[0].decode('ascii') + "  " + spaces[1].decode('ascii'))
		
		time.sleep(parameters.CM_WAIT_TIME_SEC)

	return retVal

#--------------------
#	Update the couchmart settings.py file on the pod
#--------------------
def update_settings_py(ns):
	print(divider)
	print("updating setting.py")

	name = "unknown"
	str_lit = "\\\"cb-example-{0}.cb-example.{1}.svc\\\""

	p=subprocess.Popen("{0} get pods --namespace {1}".format(COMMAND,ns), shell=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
	for line in p.stdout.readlines():
		spaces=line.split()
		if "couchmart" in spaces[0].decode('ascii') and "deploy" not in spaces[0].decode('ascii'):
			name=spaces[0].decode('ascii')
			break

	execute_command("{0} exec -it {1} --namespace {2} -- sed -e 3d -i.bkup /couchmart/settings.py".format(COMMAND,name,ns))
	execute_command("{0} exec -it {1} --namespace {2} -- sed -e \"2a AWS_NODES = [{3},{4},{5}]\" -i.bkup /couchmart/settings.py".format(
		COMMAND,name,ns,str_lit.format("0000",ns),str_lit.format("0001",ns),str_lit.format("0002",ns)))

#--------------------
#	Set up EASYRSA and generate certificates for Admission Controller in our Operator 1.2
#--------------------
def setup_rsa(ns):
	print(divider)
	print("Generating certificate for Admission Controller")

	if os.path.exists("./resources/easy-rsa"):
		execute_command("rm -rf ./resources/easy-rsa")
	execute_command("git clone https://github.com/OpenVPN/easy-rsa ./resources/easy-rsa")

	os.environ['EASYRSA_PKI']="./resources/easy-rsa/easyrsa3/pki"
	print("EASYRSA_PKI set to : {}".format(os.environ['EASYRSA_PKI']))

	execute_command("sh ./resources/easy-rsa/easyrsa3/easyrsa init-pki")

	#print("************************************************************")
	#print("	Note:  Creating Certificate Authority")
	#print("	       Enter any value: Example = Couchbase CA")
	#print("************************************************************")

	if sys.platform.startswith('freebsd') or sys.platform.startswith('linux') or sys.platform.startswith('aix') or sys.platform.startswith('darwin'):
		execute_command("sh ./resources/easy-rsa/easyrsa3/easyrsa build-ca nopass < ./resources/ca_inputs.txt")
	elif sys.platform.startswith('win32') or sys.platform.startswith('cygwin'):
		execute_command("powershell.exe -Command (Get-Content ./resources/ca_inputs.txt) | sh ./resources/easy-rsa/easyrsa3/easyrsa build-ca nopass")
	else:
		execute_command("sh ./resources/easy-rsa/easyrsa3/easyrsa build-ca nopass")

	execute_command("sh ./resources/easy-rsa/easyrsa3/easyrsa --subject-alt-name=\"DNS:*.cb-example.{0}.svc,DNS:*.{0}.svc\" build-server-full couchbase-server nopass".format(ns))

	execute_command("openssl rsa -in ./resources/easy-rsa/easyrsa3/pki/private/couchbase-server.key -out ./resources/easy-rsa/easyrsa3/pki/private/pkey.key.der -outform DER")
	execute_command("openssl rsa -in ./resources/easy-rsa/easyrsa3/pki/private/pkey.key.der -inform DER -out ./resources/easy-rsa/easyrsa3/pki/private/pkey.key -outform PEM")

	execute_command("cp -p ./resources/easy-rsa/easyrsa3/pki/issued/couchbase-server.crt ./resources/easy-rsa/easyrsa3/pki/issued/chain.pem")
	execute_command("cp -p ./resources/easy-rsa/easyrsa3/pki/issued/couchbase-server.crt ./resources/easy-rsa/easyrsa3/pki/issued/tls-cert-file")
	execute_command("cp -p ./resources/easy-rsa/easyrsa3/pki/private/pkey.key ./resources/easy-rsa/easyrsa3/pki/private/tls-private-key-file")

	PRIVATE_PATH="./resources/easy-rsa/easyrsa3/pki/private"
	ISSUED_PATH="./resources/easy-rsa/easyrsa3/pki/issued"

	execute_command("{0} create secret generic couchbase-server-tls --from-file {1} --from-file {2} --namespace {3}".format(
		COMMAND,PRIVATE_PATH+"/pkey.key",ISSUED_PATH+"/chain.pem",ns)) 

	execute_command("{0} create secret generic couchbase-operator-admission --from-file {1} --from-file {2} --namespace {3}".format(
		COMMAND,ISSUED_PATH+"/tls-cert-file",PRIVATE_PATH+"/tls-private-key-file",ns)) 

	execute_command("{0} create secret generic couchbase-operator-tls --from-file {1} --namespace {2}".format(
		COMMAND,"./resources/easy-rsa/easyrsa3/pki/ca.crt",ns))

#--------------------
#	Update the admission controller yaml from the template
#--------------------
def setup_admission_controller(ns,OP_PATH):
	print(divider)
	
	if COMMAND == "oc":
		ADMISSION_FILE=OP_PATH+"/openshift/admission.yaml"
	else:
		ADMISSION_FILE=OP_PATH+"/k8s/admission.yaml"

	execute_command("cp -fp {0}.template {0}".format(ADMISSION_FILE))
	execute_command("sed -e \"s/###NAMESPACE###/{0}/g\" -i.bkup {1}".format(ns,ADMISSION_FILE))

	execute_command("base64 ./resources/easy-rsa/easyrsa3/pki/issued/tls-cert-file > ./resources/easy-rsa/easyrsa3/pki/issued/tls-cert-file-base64")

	with open('./resources/easy-rsa/easyrsa3/pki/issued/tls-cert-file-base64', 'r') as file:
    		caBundle = file.read().replace('\n', '')

	execute_command("sed -e \"s/###CABUNDLE###/{0}/g\" -i.bkup {1}".format(caBundle,ADMISSION_FILE))

#--------------------
#	Deploy Couchbase Autonomous Operator 1.1
#--------------------
def deploy_op_1_1(ns,OP_PATH):
	print(divider)
	execute_command("{0} create -f {1}/serviceaccount-couchbase.yaml --namespace {2}".format(COMMAND,OP_PATH,ns))
	if se_user:
		execute_command("{0} create -f {1}/cluster-role.yaml --namespace {2}".format(COMMAND,OP_PATH,ns))

	execute_command("{0} create -f {1}/rolebinding.yaml --namespace {2}".format(COMMAND,OP_PATH,ns))

	# Cluster level resource only needs to be run once
	if se_user:
		execute_command("{0} create -f {1}/crd.yaml --namespace {2}".format(COMMAND,OP_PATH,ns))

	execute_command("{0} create -f {1}/operator.yaml --namespace {2}".format(COMMAND,OP_PATH,ns))
	execute_command("{0} create -f {1}/secret.yaml --namespace {2}".format(COMMAND,OP_PATH,ns))

#--------------------
#	Deploy Couchbase Autonomous Operator 1.2
#--------------------
def deploy_op_1_2(ns,OP_PATH):
	print(divider)

	if COMMAND == "oc":
		OP_PATH=OP_PATH+"/openshift"
	else:
		OP_PATH=OP_PATH+"/k8s"
	
	if se_user:
		execute_command("{0} create -f {1}/couchbase-operator-admission.yaml --namespace {2}".format(COMMAND,OP_PATH,ns))
		execute_command("{0} create -f {1}/crd.yaml --namespace {2}".format(COMMAND,OP_PATH,ns))

	execute_command("{0} create -f {1}/admission.yaml --namespace {2}".format(COMMAND,OP_PATH,ns))
	execute_command("{0} create -f {1}/operator-role.yaml --namespace {2}".format(COMMAND,OP_PATH,ns))
	execute_command("{0} create -f {1}/operator-service-account.yaml --namespace {2}".format(COMMAND,OP_PATH,ns))

	execute_command("cp -fp {0}.template {0}".format(OP_PATH+"/operator-role-binding.yaml"))
	execute_command("sed -e \"s/###NAMESPACE###/{0}/g\" -i.bkup {1}".format(ns,OP_PATH+"/operator-role-binding.yaml"))
	execute_command("{0} create -f {1}/operator-role-binding.yaml --namespace {2}".format(COMMAND,OP_PATH,ns))
	execute_command("{0} create -f {1}/operator-deployment.yaml --namespace {2}".format(COMMAND,OP_PATH,ns))
	
	execute_command("{0} create -f {1}/secret.yaml --namespace {2}".format(COMMAND,OP_PATH,ns))


#--------------------
#	Print Usage
#--------------------
def usage():
	print("python eks_script.py [--create-crd] [--create-cb-cluster] [--no-couchmart] [-h|--help]")
	print("version: {}".format(version))
	print("")
	print("	--create-crd  		== Create the cluster level resources such as CRD and ClusterRole")
	print("	--create-cb-cluster	== Create the couchbase cluster automatically")
	print("	--no-couchmart		== Disable creation of the Couchmart demo application pod")

#-------------------------------#
#	Main Program
#-------------------------------#
if __name__ == "__main__":

	#----------------------------------
	#  Pull information from Parameters
	#----------------------------------
	try:
		COMMAND=parameters.COMMAND
	except AttributeError:
		COMMAND="kubectl"

	try:
		OP_VER=parameters.OPERATOR_VERSION
	except AttributeError:
		OP_VER=1.2

	try:
		if float(OP_VER) == 1.1:
			OP_PATH="./resources/operator_1.1"
		else:
			OP_PATH="./resources/operator_1.2"
	except ValueError:
		OP_VER=1.2
		OP_PATH="./resources/operator_1.2"
	

	print("Running command : [{0}] with operator version [{1}]".format(COMMAND,OP_PATH))

	#----------------------------------
	#	Parse Arguments
	#----------------------------------
	for x in sys.argv:
		y = x.upper()
		if y == "SEUSER" or y == "--CREATE-CRD":
			se_user = True
		elif y == "--CREATE-CB-CLUSTER":
			create_cluster = True
		elif y == "--NO-COUCHMART":
			create_couchmart = False
		elif y == "EKS_SCRIPT.PY":
			continue
		elif y == "-H" or y == "--HELP":
			usage()
			sys.exit(0)
		else:
			print ("Unknown flag {}".format(x))
			usage()
			sys.exit(1)
		

	#----------------------------------
	#	Deploy to K8S or Openshift
	#----------------------------------
	ns = check_ns()
	if len(ns) <= 0:
		print("Namespace was already detected or cant be blank")
		sys.exit()

	create_namespace_yaml()
	execute_command("{0} create -f ./resources/namespace.yaml".format(COMMAND))

	if float(OP_VER) >= 1.2:
		setup_rsa(ns)
		setup_admission_controller(ns,OP_PATH)
		deploy_op_1_2(ns,OP_PATH)
	else:
		deploy_op_1_1(ns,OP_PATH)


	#-------------------------------------------
	# Shared Steps
	#-------------------------------------------
	#Launch Couchmart Environment
	try:
		tag=parameters.COUCHMART_TAG
	except AttributeError:
		tag="python2"

	if create_couchmart:
		print(divider)
		print("Creating couchmart from cbck/couchmart:{}".format(tag))
		execute_command("{0} run couchmart --image=cbck/couchmart:{1} --namespace {2}".format(COMMAND,tag,ns))	

		print(divider)
		print("Checking completion status of couchmart pod")
		if check_status(ns) == True:
			update_settings_py(ns)
		else:
			print("No running Couchmart Pod detected...")

	if create_cluster:
		if float(OP_VER) >= 1.2:
			if COMMAND == "oc":
				execute_command("{0} create -f {1}/couchbase-cluster.yaml --namespace {2}".format(COMMAND,OP_PATH+"/openshift",ns))
			else:
				execute_command("{0} create -f {1}/couchbase-cluster.yaml --namespace {2}".format(COMMAND,OP_PATH+"/k8s",ns))
		else:
			if COMMAND == "oc":
				execute_command("{0} create -f {1}/couchbase-cluster-OC.yaml --namespace {2}".format(COMMAND,OP_PATH,ns))
			else:
				execute_command("{0} create -f {1}/couchbase-cluster.yaml --namespace {2}".format(COMMAND,OP_PATH,ns))
