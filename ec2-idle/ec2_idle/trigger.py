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
                        f"{instance['InstanceId']}: Instance is exempt from idle shutdown"
                    )
                    return True

                elif str(t["Value"]).upper() == "FALSE":
                    logging.warning(
                        f"{instance['InstanceId']}: Instance is explicitly NOT exempt from idle shutdown"
                    )
                    return False

                else:
                    logging.warning(
                        f"{instance['InstanceId']}: Found unrecognised tag value: {t['Value']}.  Defaulting to NOT exempt"
                    )
                    return False

        # there were tags, but not the one we're looking for
        logging.warning(
            f"{instance['InstanceId']}: Did not find tag IDLE_EXEMPT.  Defaulting to NOT exempt"
        )
        return False

    except Exception as e:
        # no tags, so default to not idle exempt
        logging.warning(
            f"{instance['InstanceId']}: No tags on this instance, so did not find tag IDLE_EXEMPT.  Defaulting to NOT exempt",
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
        logging.warning(f"Found {len(instDict)} reservations")
        for r in instDict["Reservations"]:
            logging.warning(f"Found {len(r)} instances")
            for i in r["Instances"]:
                if isIdleExempt(instance=i):
                    logging.warning(
                        f"{i['InstanceId']}: Instance is idle exempt, skipping"
                    )
                else:
                    logging.warning(f"{i['InstanceId']}: Instance is NOT idle exempt")
                    matchedInstances.append(i)
    except Exception as e:
        logging.error(
            "Did not find Reservations or Instances key in Dictionary.  Terminating."
        )
        logging.error(str(e))
        raise

    logging.warning("Finished iterating ec2 instances, now beginning invoke")
    # Invoke worker function for each IP address
    lambdaClient = boto3.client("lambda")
    for host in matchedInstances:
        jsonPayload = {}
        jsonPayload["IP"] = host["PrivateIpAddress"]
        jsonPayload["InstanceId"] = host["InstanceId"]

        logging.warning(f"{host['PrivateIpAddress']}: Invoking worker_function")
        payload = json.dumps(jsonPayload)
        logging.warning(f"{host['PrivateIpAddress']}: Payload set")
        invokeResponse = lambdaClient.invoke(
            FunctionName="arn:aws:lambda:us-west-2:036372598227:function:ec2-idle-shutdown-WorkerFunction-w6PPXXX7z4xA:ec2-idle-worker",
            InvocationType="Event",
            LogType="Tail",
            Payload=payload,
        )
        logging.warning(
            f"{host['PrivateIpAddress']}: Finished.  Response: {invokeResponse}"
        )

    logging.warning("trigger_handler complete")

    return {"statusCode": 200, "body": json.dumps("Success")}


if __name__ == "__main__":
    trigger_handler("", "")
