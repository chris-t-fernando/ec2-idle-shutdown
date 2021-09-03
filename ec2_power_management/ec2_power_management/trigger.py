import boto3
import logging, sys
import json
import datetime
from pytz import timezone


def isIdleExempt(instance):
    try:
        for t in instance["Tags"]:
            if str(t["Key"]).upper() == "IDLE_EXEMPT":
                # found the tag we want
                if str(t["Value"]).upper() == "TRUE":
                    # true - exempt from idle shutdown
                    logging.warning(
                        f"[Power off] {instance['InstanceId']}: Instance is exempt from idle shutdown"
                    )
                    return True

                elif str(t["Value"]).upper() == "FALSE":
                    logging.warning(
                        f"[Power off] {instance['InstanceId']}: Instance is explicitly NOT exempt from idle shutdown"
                    )
                    return False

                else:
                    logging.warning(
                        f"[Power off] {instance['InstanceId']}: Found unrecognised tag value: {t['Value']}.  Defaulting to NOT exempt"
                    )
                    return False

        # there were tags, but not the one we're looking for
        logging.warning(
            f"[Power off] {instance['InstanceId']}: Did not find tag IDLE_EXEMPT.  Defaulting to NOT exempt"
        )
        return False

    except Exception as e:
        # no tags, so default to not idle exempt
        logging.warning(
            f"[Power off] {instance['InstanceId']}: No tags on this instance.  Defaulting to NOT exempt",
        )
        return False


def isScheduledPowerOn(instance):
    try:
        powerOnConditionMet = False
        dayConditionMet = False
        hourConditionMet = False
        for t in instance["Tags"]:
            if (
                str(t["Key"]).upper() == "EC2_POWERON"
                and str(t["Value"]).upper() == "TRUE"
            ):
                powerOnConditionMet = True
                logging.warning(
                    f"[Power on] {instance['InstanceId']}: Met EC2_POWERON tag condition"
                )

            if str(t["Key"]).upper() == "EC2_POWERON_SCHEDULE":
                try:
                    schedule_json = json.loads(t["Value"])
                    if (
                        "hour" not in schedule_json.keys()
                        or "day" not in schedule_json.keys()
                    ):
                        logging.error(
                            f"[Power on] {instance['InstanceId']}: EC2_POWERON_SCHEDULE json must include 'hour' and 'day' keys.  json: {t['Value']}"
                        )
                        return False

                    try:
                        int(schedule_json["hour"])
                    except Exception as e:
                        logging.error(
                            f"[Power on] {instance['InstanceId']}: EC2_POWERON_SCHEDULE 'hour' value must be an integer.  json: {t['Value']}"
                        )
                        raise

                    if int(schedule_json["hour"]) > 23:
                        logging.error(
                            f"[Power on] {instance['InstanceId']}: EC2_POWERON_SCHEDULE 'hour' value must be <24.  json: {t['Value']}"
                        )
                        return False

                    if (
                        str(schedule_json["day"]).upper()
                        == str(datetime.datetime.today().strftime("%A")).upper()
                    ):
                        dayConditionMet = True

                    now = datetime.datetime.now(timezone("Australia/Melbourne"))
                    if now.hour == int(schedule_json["hour"]):
                        hourConditionMet = True

                    logging.error(
                        f"[Power on] {instance['InstanceId']}: EC2_POWERON_SCHEDULE contains valid json schedule: {t['Value']}"
                    )

                except Exception as e:
                    # bad json
                    logging.error(
                        f"[Power on] {instance['InstanceId']}: Found EC2_POWERON_SCHEDULE tag, but could not parse content as JSON - ignoring.  Found: {t['Value']}"
                    )
                    return False

        # finished looking for tags, see if we found them
        if powerOnConditionMet and dayConditionMet and hourConditionMet:
            # matched so do it
            logging.warning(
                f"[Power on] {instance['InstanceId']}: Satisfied EC2_POWERON and EC2_POWERON_SCHEDULE conditions"
            )
            return True

        else:
            if not powerOnConditionMet:
                logging.warning(
                    f"[Power on] {instance['InstanceId']}: Did not satisfy EC2_POWERON condition"
                )
            if not dayConditionMet:
                logging.warning(
                    f"[Power on] {instance['InstanceId']}: Did not satisfy EC2_POWERON_SCHEDULE day condition"
                )
            if not hourConditionMet:
                logging.warning(
                    f"[Power on] {instance['InstanceId']}: Did not satisfy EC2_POWERON_SCHEDULE hour condition"
                )
            return False

    except Exception as e:
        logging.error(
            f"[Power on] {instance['InstanceId']}: No tags on this instance.  Defaulting to NO schedule"
        )
        logging.error(str(e))
        return False


def trigger_handler(event, context):
    logging.basicConfig(stream=sys.stderr, level=logging.INFO)
    logging.warning("Beginning trigger_handler")

    ec2Client = boto3.client("ec2")
    # i don't like this since its case sensitive for both keys and values
    # instDict=client.describe_instances(
    #        Filters=[{'Name':'tag:Environment','Values':['Dev']}]
    #    )

    logging.warning("[Power off] Beginning power off")

    matchedPowerOffInstances = []
    instDict = ec2Client.describe_instances(
        Filters=[{"Name": "instance-state-name", "Values": ["running"]}]
    )
    logging.warning("[Power off] Ran describe instances")
    try:
        logging.warning(f"[Power off] Found {len(instDict)} reservations")
        for r in instDict["Reservations"]:
            logging.warning(f"[Power off] Found {len(r)} instances")
            for i in r["Instances"]:
                if isIdleExempt(instance=i):
                    logging.warning(
                        f"[Power off] {i['InstanceId']}: Instance is idle exempt, skipping"
                    )
                else:
                    logging.warning(
                        f"[Power off] {i['InstanceId']}: Instance is NOT idle exempt"
                    )
                    matchedPowerOffInstances.append(i)
    except Exception as e:
        logging.error(
            "[Power off] Did not find Reservations or Instances key in Dictionary.  Terminating."
        )
        logging.error(str(e))
        raise

    logging.warning(
        "[Power off] Finished iterating ec2 instances, now beginning invoke"
    )
    # Invoke worker function for each IP address
    lambdaClient = boto3.client("lambda")
    for host in matchedPowerOffInstances:
        jsonPayload = {}
        jsonPayload["IP"] = host["PublicIpAddress"]
        jsonPayload["InstanceId"] = host["InstanceId"]

        logging.warning(
            f"[Power off] {host['PublicIpAddress']}: Invoking worker_function"
        )
        payload = json.dumps(jsonPayload)
        logging.warning(f"[Power off] {host['PublicIpAddress']}: Payload set")
        invokeResponse = lambdaClient.invoke(
            FunctionName="arn:aws:lambda:us-west-2:036372598227:function:ec2-power-management-WorkerFunction-xKBC7O6FaPHC",
            InvocationType="Event",
            LogType="Tail",
            Payload=payload,
        )
        logging.warning(
            f"[Power off] {host['PublicIpAddress']}: Finished.  Response: {invokeResponse}"
        )
    if len(matchedPowerOffInstances) == 0:
        logging.warning("[Power off] No instances online.  Finished successfully.")
    else:
        logging.warning(
            "[Power off] Successfully issued shutdown commands.  Finished power off"
        )

    # i could combine the power off and on logic but this feels cleaner, easier to maintain even if its a bit heavy handed
    logging.warning("[Power on] Beginning power on")

    matchedPowerOffInstances = []
    instDict = ec2Client.describe_instances(
        Filters=[{"Name": "instance-state-name", "Values": ["stopped"]}]
    )

    logging.warning("[Power on] Ran describe instances")
    try:
        logging.warning(f"[Power on] Found {len(instDict)} instances")
        for r in instDict["Reservations"]:
            logging.warning(
                f"[Power on] Found {len(r)} reservations and {len(r['Instances'])} instance"
            )
            for i in r["Instances"]:
                if isScheduledPowerOn(instance=i):
                    try:
                        powerOnInstances = [i["InstanceId"]]
                        ec2Client.start_instances(InstanceIds=powerOnInstances)
                        logging.warning(
                            f"[Power on] {i['InstanceId']} Met dayCondition and hourCondition, successfully issued power on command"
                        )
                    except Exception as e:
                        logging.error(
                            f"[Power on] {i['InstanceId']} Failed to power on instance"
                        )
                        logging.error(str(e))
                        raise

                else:
                    # don't do the thing
                    logging.warning(
                        f"[Power on] {i['InstanceId']} Not tagged for power on, skipping"
                    )

            logging.warning(f"[Power on] Finished iterating ec2 instances")

    except Exception as e:
        logging.error(
            "[Power on] Did not find Reservations or Instances key in Dictionary.  Terminating."
        )
        logging.error(str(e))
        raise

    logging.warning(f"[Power on] Successfully processed startups")
    return {"statusCode": 200, "body": json.dumps("Success")}


if __name__ == "__main__":
    trigger_handler("", "")
