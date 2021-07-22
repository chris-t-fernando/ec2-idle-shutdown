import boto3
import paramiko
import logging, sys


def worker_handler(event, context):
    logging.basicConfig(stream=sys.stderr, level=logging.WARNING)

    s3Client = boto3.client("s3")
    # Download private key file from secure S3 bucket
    s3Client.download_file("fdotech", "ssh_keys/chris2.pem", "/tmp/keyname.pem")
    #s3Client.download_file("fdotech", "ssh_keys/chris2.pem", "y:\\keyname.pem")
    logging.warning("%s: Got pem file from S3", event["IP"])

    k = paramiko.RSAKey.from_private_key_file("/tmp/keyname.pem")
    #k = paramiko.RSAKey.from_private_key_file("y:\\keyname.pem")
    c = paramiko.SSHClient()

    c.set_missing_host_key_policy(paramiko.AutoAddPolicy())

    host = event["IP"]
    c.connect(hostname=host, username="ubuntu", pkey=k)
    logging.warning("%s: Connected via SSH", host)

    command = "uptime"
    stdin, stdout, stderr = c.exec_command(command)
    uptimeResult = stdout.read()
    uptimeResult = uptimeResult.decode("utf-8")

    logging.warning("%s: Uptime output is: %s", host, uptimeResult)

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
            "{host}: Server has been online for {minutes} minutes - has not met uptime condition".format(
                host=host, minutes=uptimeList[2]
            )
        )
    elif ":" in uptimeList[2]:
        # up for less than a day
        colLocation = uptimeList[2].find(":")

        # just get hours
        strPositionTwo = str(uptimeList[2])
        hoursUptime = strPositionTwo[:colLocation]

        if int(hoursUptime) > 1:
            # been up for more than an hour
            uptimeConditionMet = True
            logging.warning(
                "{host}: Server has been online for {hours} hours - met uptime condition".format(
                    host=host, hours=hoursUptime
                )
            )
        else:
            # hasn't een online long enough to be deemed idle
            uptimeConditionMet = False
            logging.warning(
                "{host}: Server has been online for {hours} hours - has not met uptime condition".format(
                    host=host, hours=hoursUptime
                )
            )
    else:
        try:
            hoursUptime = int(uptimeList[2])
            uptimeConditionMet = True
            logging.warning(
                "{host}: Server has been online for {hours} hours - met uptime condition".format(
                    host=host, hours=hoursUptime
                )
            )
        except:
            logging.warning(
                "{host}: Unprocessable string found: {string}".format(
                    host=host, string=uptimeList[2]
                )
            )

    # can't rely on index, so find location of 'users' or 'user' and then go back one position
    # maybe the hackiest code I've ever written (probably not...)
    try:
        userIndex = uptimeList.index("users,") - 1
    except:
        userIndex = uptimeList.index("user,") - 1

    if int(uptimeList[userIndex]) > 0:
        # someone is logged in
        logging.warning(
            "{host}: {users} user(s) are logged in - has not met users condition".format(
                host=host, users=uptimeList[userIndex]
            )
        )
        usersConditionMet = False

    else:
        # nobody is logged in
        logging.warning(
            "{host}: No user(s) are logged in - has met users condition".format(
                host=host
            )
        )

        usersConditionMet = True

    if uptimeConditionMet and usersConditionMet:
        logging.warning("{host}: Server is deemed idle".format(host=host))
        idle = True
    else:
        logging.warning("{host}: Server is NOT deemed idle".format(host=host))
        idle = False

    if idle:
        # shut down
        try:
            ec2Client = boto3.client("ec2")
            instanceList = [event["InstanceId"]]
            ec2Client.stop_instances(InstanceIds=instanceList)
            logging.warning(
                "{host}: Successfully issued shutdown command to iIdle system".format(
                    host=host
                )
            )

        except Exception as e:
            logging.error(
                "{host}: Failed to issue shutdown command to instance {instance}.  Error: {error}".format(
                    host=host, instance=event["InstanceId"], error=str(e)
                )
            )
    else:
        # not idle, ignore
        logging.warning("{host}: Non-idle system.  Skipping".format(host=host))

    return {
        "message": "Script execution completed. See Cloudwatch logs for complete output"
    }


if __name__ == "__main__":
    worker_handler({"IP": "18.236.118.125", "InstanceId": "i-09f0a44d7455c1e65"}, "")
