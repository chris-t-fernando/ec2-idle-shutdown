import boto3
import paramiko
import logging, sys
import json


def worker_handler(event, context):
    logging.basicConfig(stream=sys.stderr, level=logging.INFO)

    s3Client = boto3.client("s3")
    # Download private key file from secure S3 bucket
    s3Client.download_file("fdotech", "ssh_keys/chris2.pem", "/tmp/keyname.pem")
    # s3Client.download_file("fdotech", "ssh_keys/chris2.pem", "y:\\keyname.pem")
    logging.warning(f"{event['IP']}: Got pem file from S3")

    k = paramiko.RSAKey.from_private_key_file("/tmp/keyname.pem")
    # k = paramiko.RSAKey.from_private_key_file("y:\\keyname.pem")
    c = paramiko.SSHClient()

    c.set_missing_host_key_policy(paramiko.AutoAddPolicy())

    host = event["IP"]
    c.connect(hostname=host, username="ubuntu", pkey=k)
    logging.warning(f"{host}: Connected via SSH")

    command = "uptime"
    stdin, stdout, stderr = c.exec_command(command)
    uptimeResult = stdout.read()
    uptimeResult = uptimeResult.decode("utf-8")

    logging.warning(f"{host}: Uptime output is: {uptimeResult}")

    uptimeList = uptimeResult.split()

    # 20:38:49 up 2 min,  0 users,  load average: 0.28, 0.25, 0.10 pass
    # 19:44:57 up 20:40,  0 users,  load average: 0.04, 0.01, 0.00 pass
    # 19:44:57 up 20:40,  1 user,  load average: 0.04, 0.01, 0.00 pass
    # 09:45:24 up 46 days, 11:51,  1 user,  load average: 0.11, 0.04, 0.01

    # if position 2 contains :, then less than 24 hours
    # otherwise, more than 1 day
    if uptimeList[3] == "min,":
        # up for less than an hour
        uptimeConditionMet = False
        logging.warning(
            f"{host}: Server has been online for {uptimeList[2]} minutes - has not met uptime condition"
        )
    elif ":" in uptimeList[2]:
        # up for less than a day
        colLocation = uptimeList[2].find(":")

        # just get hours
        strPositionTwo = str(uptimeList[2])
        hoursUptime = strPositionTwo[:colLocation]

        if int(hoursUptime) > 0:
            # been up for more than an hour
            uptimeConditionMet = True
            logging.warning(
                f"{host}: Server has been online for {hoursUptime} hours - met uptime condition"
            )
        else:
            # hasn't een online long enough to be deemed idle
            uptimeConditionMet = False
            logging.warning(
                f"{host}: Server has been online for {hoursUptime} hours - has not met uptime condition"
            )
    else:
        try:
            hoursUptime = int(uptimeList[2])
            uptimeConditionMet = True
            logging.warning(
                f"{host}: Server has been online for {hoursUptime} hours - met uptime condition"
            )
        except:
            logging.error(f"{host}: Unprocessable string found: {uptimeList[2]}")

    # can't rely on index, so find location of 'users' or 'user' and then go back one position
    # maybe the hackiest code I've ever written (probably not...)
    try:
        userIndex = uptimeList.index("users,") - 1
    except:
        userIndex = uptimeList.index("user,") - 1

    # >1 because jripper runs for more than an hour but will appear as 'idle'
    if int(uptimeList[userIndex]) > 1:
        # someone is logged in
        logging.warning(
            f"{host}: {uptimeList[userIndex]} user(s) are logged in - has not met users condition"
        )

        usersConditionMet = False

    else:
        # nobody is logged in
        logging.warning(f"{host}: No user(s) are logged in - has met users condition")

        usersConditionMet = True

    if uptimeConditionMet and usersConditionMet:
        logging.warning(f"{host}: Server is deemed idle")
        idle = True
    else:
        logging.warning(f"{host}: Server is NOT deemed idle")
        idle = False

    if idle:
        # shut down
        try:
            ec2Client = boto3.client("ec2")
            instanceList = [event["InstanceId"]]
            ec2Client.stop_instances(InstanceIds=instanceList)
            logging.warning(
                f"{host}: Successfully issued shutdown command to idle system"
            )

        except Exception as e:
            logging.error(
                f"{host}: Failed to issue shutdown command to instance {event['InstanceId']}.  Error: {str(e)}"
            )
            logging.error(str(e))
            raise
    else:
        # not idle, ignore
        logging.warning(f"{host}: Non-idle system.  Skipping")

    return {"statusCode": 200, "body": json.dumps("Success")}


if __name__ == "__main__":
    worker_handler({"IP": "18.236.118.125", "InstanceId": "i-09f0a44d7455c1e65"}, "")
