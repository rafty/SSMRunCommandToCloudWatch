import os
import json
import gzip
import base64
import boto3
from aws_lambda_powertools import Logger

logger = Logger()
sns_topic_arn = os.environ['SNS_TOPIC_ARN']
client = boto3.client('sns')


def get_logs_event_data(event):
    # base64 decode & decompress
    logs_data = event['awslogs']['data']
    decode_base64 = base64.b64decode(logs_data)
    decompress = gzip.decompress(decode_base64)
    data = json.loads(decompress)
    log_group = data['logGroup']
    log_stream = data['logStream']
    messages = [event['message'] for event in data['logEvents']]

    logger.info(
        (f'log_strem: {log_group}/{log_stream}\n'
         f'messages: {messages}'))

    return log_group, log_stream, messages


def extruct_parameter(log_stream: str):
    # stream name format:
    #   'CommandID/InstanceID/PluginID/stdout'
    #   'CommandID/InstanceID/PluginID/stderr'
    str_list = log_stream.rsplit('/')
    ssm_run_command = str_list[-2]
    instance_id = str_list[-3]
    return ssm_run_command, instance_id


def format_publish_message(message: str, log_group: str, log_stream: str,
                           instance_id: str):
    subject = 'CloudWatch Agent Error'
    publish_message = ('CloudWatch Agent Error.\n'
                       f'Instance ID: {instance_id}\n'
                       f'Log stream: {log_group}/{log_stream}\n'
                       f'Event Message:\n'
                       f'{message}\n')
    return subject, publish_message


@logger.inject_lambda_context(log_event=True)
def lambda_handler(event, context):
    logger.info(f'lambda_handler event: {event}')

    try:
        log_group, log_stream, messages = get_logs_event_data(event)
        ssm_run_command, instance_id = extruct_parameter(log_stream)

        if ssm_run_command not in ['ControlCloudWatchAgentLinux',
                                   'ControlCloudWatchAgentWindows']:
            return

        for message in messages:
            subject, publish_message = format_publish_message(message,
                                                              log_group,
                                                              log_stream,
                                                              instance_id)
            client.publish(
                TopicArn=sns_topic_arn,
                Subject=subject,
                Message=publish_message)

        return
    except Exception as e:
        logger.exception(e)
        raise e
