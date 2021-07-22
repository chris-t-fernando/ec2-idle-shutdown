import boto3
import logging, sys
import json

logging.basicConfig(stream=sys.stderr, level=logging.WARNING)


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
    logging.error("Starting up")
    ec2Client = boto3.client("ec2")

    # i don't like this since its case sensitive for both keys and values
    # instDict=client.describe_instances(
    #        Filters=[{'Name':'tag:Environment','Values':['Dev']}]
    #    )

    matchedInstances = []
    instDict = ec2Client.describe_instances()
    logging.error("Ran describe instances")
    try:
        for r in instDict["Reservations"]:
            for i in r["Instances"]:
                if isIdleExempt(instance=i):
                    logging.error(
                        "%s: Instance is idle exempt, skipping", i["InstanceId"]
                    )
                else:
                    logging.error("%s: Instance is NOT idle exempt", i["InstanceId"])
                    matchedInstances.append(i)
    except Exception as e:
        logging.error(
            "Did not find Reservations or Instances key in Dictionary.  Terminating."
        )
        print(str(e))
        return False

    logging.error("Finished iterating ec2 instances, now beginning invoke")
    # Invoke worker function for each IP address
    lambdaClient = boto3.client("lambda")
    for host in matchedInstances:
        jsonPayload = {}
        jsonPayload["IP"] = host["PrivateIpAddress"]
        jsonPayload["InstanceId"] = host["InstanceId"]

        print("Invoking worker_function on %s", host["PrivateIpAddress"])
        invokeResponse = lambdaClient.invoke(
            FunctionName="worker_function",
            InvocationType="Event",
            LogType="Tail",
            Payload=json.dumps(jsonPayload),
        )
        print(invokeResponse)

    return {"message": "Trigger function finished"}


if __name__ == "__main__":
    trigger_handler("", "")
