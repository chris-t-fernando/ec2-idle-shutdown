import boto3
import logging, sys
import json


def isIdleExempt(instance):
    try:
        for t in instance["Tags"]:
            if str(t["Key"]).upper() == "IDLE_EXEMPT":
                # found the tag we want
                if str(t["Value"]).upper() == "TRUE":
                    # true - exempt from idle shutdown
                    logging.warning(
                        "%s: Instance is exempt from idle shutdown",
                        instance["InstanceId"],
                    )
                    return True

                elif str(t["Value"]).upper() == "FALSE":
                    logging.warning(
                        "%s: Instance is explicitly NOT exempt from idle shutdown",
                        instance["InstanceId"],
                    )
                    return False

                else:
                    logging.warning(
                        "%s: Found unrecognised tag value: %s.  Defaulting to NOT exempt",
                        instance["InstanceId"],
                        t["Value"],
                    )
                    return False

        # there were tags, but not the one we're looking for
        logging.warning(
            "%s: Did not find tag IDLE_EXEMPT.  Defaulting to NOT exempt",
            instance["InstanceId"],
        )
        return False

    except Exception as e:
        # no tags, so default to not idle exempt
        logging.warning(
            "%s: No tags on this instance, so did not find tag IDLE_EXEMPT.  Defaulting to NOT exempt",
            instance["InstanceId"],
        )
        return False


def trigger_handler(event, context):
    logging.basicConfig(stream=sys.stderr, level=logging.INFO)
    logging.warning("Beginning trigger_handler")
    ec2Client = boto3.client("ec2")

    # i don't like this since its case sensitive for both keys and values
    # instDict=client.describe_instances(
    #        Filters=[{'Name':'tag:Environment','Values':['Dev']}]
    #    )

    matchedInstances = []
    instDict = ec2Client.describe_instances()
    logging.warning("Ran describe instances")
    try:
        logging.warning("Found {len} reservations".format(len=len(instDict)))
        for r in instDict["Reservations"]:
            logging.warning("Found {len} instances".format(len=len(r)))
            for i in r["Instances"]:
                if isIdleExempt(instance=i):
                    logging.warning(
                        "%s: Instance is idle exempt, skipping", i["InstanceId"]
                    )
                else:
                    logging.warning("%s: Instance is NOT idle exempt", i["InstanceId"])
                    matchedInstances.append(i)
    except Exception as e:
        logging.error(
            "Did not find Reservations or Instances key in Dictionary.  Terminating."
        )
        logging.error(str(e))
        return False

    logging.warning("Finished iterating ec2 instances, now beginning invoke")
    # Invoke worker function for each IP address
    lambdaClient = boto3.client("lambda")
    for host in matchedInstances:
        jsonPayload = {}
        jsonPayload["IP"] = host["PrivateIpAddress"]
        jsonPayload["InstanceId"] = host["InstanceId"]

        logging.warning(
            "{host}: Invoking worker_function".format(host=host["PrivateIpAddress"])
        )
        invokeResponse = lambdaClient.invoke(
            # FunctionName="worker_function",
            FunctionName="arn:aws:lambda:us-west-2:036372598227:function:ec2-idle-WorkerFunction-FVTGj1iqS1LH",
            InvocationType="RequestResponse",
            LogType="Tail",
            Payload=json.dumps(jsonPayload),
        )
        logging.warning(
            "{host}: Finished.  Response: {response}".format(
                host=host["PrivateIpAddress"], response=invokeResponse
            )
        )

    logging.warning("trigger_handler complete")

    return {"message": "Trigger function finished"}


if __name__ == "__main__":
    trigger_handler("", "")
