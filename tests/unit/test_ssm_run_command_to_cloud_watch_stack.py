import aws_cdk as core
import aws_cdk.assertions as assertions

from _stacks.ssm_run_command_to_cloud_watch_stack import SsmRunCommandToCloudWatchStack

# example tests. To run these tests, uncomment this file along with the example
# resource in ssm_run_command_to_cloud_watch/ssm_run_command_to_cloud_watch_stack.py
def test_sqs_queue_created():
    app = core.App()
    stack = SsmRunCommandToCloudWatchStack(app, "ssm-run-command-to-cloud-watch")
    template = assertions.Template.from_stack(stack)

#     template.has_resource_properties("AWS::SQS::Queue", {
#         "VisibilityTimeout": 300
#     })
