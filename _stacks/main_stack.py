import aws_cdk
from aws_cdk import Stack
from constructs import Construct
from aws_cdk import aws_ec2
from aws_cdk import aws_iam
from aws_cdk import Tags
from aws_cdk import aws_ssm
from aws_cdk import aws_logs
from aws_cdk import aws_logs_destinations
from aws_cdk import aws_cloudwatch
from aws_cdk import aws_sns
from aws_cdk import aws_sns_subscriptions
from aws_cdk import aws_cloudwatch_actions
from aws_cdk import aws_lambda


class MainStack(Stack):

    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        self._configuration = {
            'vpc_cidr': '10.10.0.0/16',
        }
        self._resources = {
            # 'vpc': None,
            # 'instance': None
        }

        self.create_vpc()
        self.create_instance()
        self.set_tag_to_instance()
        self.create_ssm_maintenance_window()
        self.create_logs_lambda_subscription_filter()
        # self.create_logs_metrics_alarm()

    def create_vpc(self):
        # --------------------------------------------------------------
        # VPC - Three Tire Network
        # --------------------------------------------------------------
        _vpc = aws_ec2.Vpc(
            self,
            'TestVpc',
            cidr=self._configuration.get('vpc_cidr'),
            max_azs=1,
            nat_gateways=0,
            subnet_configuration=[
                aws_ec2.SubnetConfiguration(
                    name="Front",
                    subnet_type=aws_ec2.SubnetType.PUBLIC,
                    cidr_mask=24),
            ]
        )
        self._resources['vpc'] = _vpc

    def create_instance(self):
        # Security Group
        _sg = aws_ec2.SecurityGroup(
            self,
            'TestSecurityGroup',
            security_group_name='test_sg',
            vpc=self._resources.get('vpc'),
            allow_all_outbound=True
        )
        _sg.add_ingress_rule(
            peer=aws_ec2.Peer.any_ipv4(),
            connection=aws_ec2.Port.tcp(80)
        )
        _sg.add_ingress_rule(
            peer=aws_ec2.Peer.any_ipv4(),
            connection=aws_ec2.Port.tcp(443)
        )
        # IAM Role
        _role = aws_iam.Role(
            self,
            'SsmRunCommandTest',
            assumed_by=aws_iam.ServicePrincipal('ec2.amazonaws.com'),
            managed_policies=[
                aws_iam.ManagedPolicy.from_aws_managed_policy_name(
                    'AmazonSSMManagedInstanceCore'),
                aws_iam.ManagedPolicy.from_aws_managed_policy_name(
                    'CloudWatchAgentServerPolicy'
                )
            ]
        )
        # EC2 Instance
        _instance_type = aws_ec2.InstanceType('t3.micro')
        _subnet = aws_ec2.SubnetSelection(
            subnet_type=aws_ec2.SubnetType.PUBLIC
        )
        _ami = aws_ec2.AmazonLinuxImage(
            generation=aws_ec2.AmazonLinuxGeneration.AMAZON_LINUX_2,
        )
        _instance = aws_ec2.Instance(
            self,
            'TestInstance',
            instance_name='TestInstanceForSsmRunCommand',
            vpc=self._resources.get('vpc'),
            instance_type=_instance_type,
            vpc_subnets=_subnet,
            security_group=_sg,
            role=_role,
            machine_image=_ami
        )
        self._resources['instance'] = _instance

    # ===========================================================
    # Tag - EC2 Instance
    # ===========================================================
    def set_tag_to_instance(self):
        Tags.of(self._resources.get('instance')).add(
            'MonitoringCloudWatchAgent', 'True'
        )

    # ===========================================================
    # SSM MaintenanceWindow
    # ===========================================================
    def create_ssm_maintenance_window(self):
        # Create MaintenanceWindow
        _maintenance_window = aws_ssm.CfnMaintenanceWindow(
            self,
            'MaintenanceWindow',
            name='MonitoringCloudWatchAgent',
            description='CheckCloudWatchAgent',
            cutoff=1,  # hour
            duration=2,  # hour
            schedule='cron(0/10 * * * ? *)',
            allow_unassociated_targets=False,
        )
        # MaintenanceWindow Target
        _target = aws_ssm.CfnMaintenanceWindowTarget(
            self,
            'MaintenanceTarget',
            name='MonitoringCloudWatchAgent',
            resource_type='INSTANCE',
            targets=[
                {
                    'key': 'tag:MonitoringCloudWatchAgent',
                    'values': ['True']
                },
            ],
            window_id=_maintenance_window.ref
        )
        # MaintenanceWindow task
        _maintenance_window_task = aws_ssm.CfnMaintenanceWindowTask(
            self,
            'MaintenanceTask',
            priority=0,
            task_arn='AmazonCloudWatch-ManageAgent',
            task_type='RUN_COMMAND',
            window_id=_maintenance_window.ref,
            max_concurrency='1000',
            max_errors='2',
            name='MonitoringCloudWatchAgent',
            # service_role_arn='',  # for SNS
            targets=[aws_ssm.CfnMaintenanceWindowTask.TargetProperty(
                key='WindowTargetIds', values=[_target.ref])],
            task_invocation_parameters=aws_ssm.CfnMaintenanceWindowTask.TaskInvocationParametersProperty(
                maintenance_window_run_command_parameters=aws_ssm.CfnMaintenanceWindowTask.MaintenanceWindowRunCommandParametersProperty(
                    parameters={
                        'action': ['status'],
                        'mode': ['ec2'],
                        'optionalConfigurationSource': ['default'],
                        'optionalConfigurationLocation': [''],
                        'optionalOpenTelemetryCollectorConfigurationSource': [
                            'ssm'],
                        'optionalOpenTelemetryCollectorConfigurationLocation': [
                            ''],
                        'optionalRestart': ['yes']
                    },
                    cloud_watch_output_config=aws_ssm.CfnMaintenanceWindowTask.CloudWatchOutputConfigProperty(
                        cloud_watch_output_enabled=True,
                        # cloud_watch_log_group_name='hoge'
                    ),
                )
            ),
        )

    # ===========================================================
    # AWS CloudWatch Logs - Subscription Filter
    # ===========================================================
    def create_logs_lambda_subscription_filter(self):
        # SNS Topic for Alart Mail
        _topic = aws_sns.Topic(
            self,
            'CloudWatchAgentAlarmTopic',
            topic_name='cloudwatch_agent_alart',
            display_name='cloudwatch_agent_alart'
        )
        _topic.add_subscription(
            aws_sns_subscriptions.EmailSubscription(
                'yagita.takashi+alert@gmail.com'
            ))
        # AWS Lambda function for logs subscription filter
        _powertools_layer = aws_lambda.LayerVersion.from_layer_version_arn(
            self,
            id='lambda-powertools',
            layer_version_arn=(f'arn:aws:lambda:{self.region}:017000801446:'
                               'layer:AWSLambdaPowertoolsPython:19')
        )
        _function = aws_lambda.Function(
            self,
            'CloudWatchLogsForwarder',
            function_name='cloudwatch_forwarder',
            handler='function.lambda_handler',
            runtime=aws_lambda.Runtime.PYTHON_3_9,
            code=aws_lambda.Code.from_asset('./functions/forwarder'),
            layers=[_powertools_layer],
            environment={
                'SNS_TOPIC_ARN': _topic.topic_arn,
                'POWERTOOLS_SERVICE_NAME': 'health_check',
                'LOG_LEVEL': 'INFO',
            }
        )
        _topic.grant_publish(_function)

        # Logs Subscription Log Group
        _log_group = aws_logs.LogGroup(
            self,
            'LogGroup',
            log_group_name='/aws/ssm/AmazonCloudWatch-ManageAgent',
            removal_policy=aws_cdk.RemovalPolicy.DESTROY
        )

        # JSON Filter Pattern for Logs Subscription Filter
        json_filter_pattern = aws_logs.FilterPattern.any(
            aws_logs.FilterPattern.string_value(
                json_field='$.status',
                comparison='=',
                value='stopped'
            )
        )
        aws_logs.SubscriptionFilter(
            self,
            'LambdaSubscriptionFilterJson',
            log_group=_log_group,
            destination=aws_logs_destinations.LambdaDestination(_function),
            filter_pattern=json_filter_pattern
        )
        # String log Filter Pattern for Logs Subscription Filter
        string_filter_pattern = aws_logs.FilterPattern.any(
            aws_logs.FilterPattern.any_term('CloudWatch Agent not installed.')
        )
        aws_logs.SubscriptionFilter(
            self,
            'LambdaSubscriptionFilterString',
            log_group=_log_group,
            destination=aws_logs_destinations.LambdaDestination(_function),
            filter_pattern=string_filter_pattern
        )

    def create_logs_metrics_alarm(self):
        # ログイベントのメトリクスだけで、データの中身は見れない。
        # no use
        _log_group = aws_logs.LogGroup(
            self,
            'LogGroup',
            log_group_name='/aws/ssm/AmazonCloudWatch-ManageAgent',
            removal_policy=aws_cdk.RemovalPolicy.DESTROY
        )
        _metric_filter = aws_logs.MetricFilter(
            'MetricsFilter',
            log_group=_log_group,
            filter_pattern=aws_logs.FilterPattern.all_terms('stopped',
                                                            'status'),
            metric_namespace='MyApp',
            metric_name='CWAgentStatus',
            metric_value='1'
        )
        _metric = _metric_filter.metric(
            period=aws_cdk.Duration.minutes(5),
            statistic='sum',
            unit=aws_cloudwatch.Unit('COUNT')
        )
        _topic = aws_sns.Topic(
            self,
            'MyTopic',
            topic_name='cloudwatch_agent_alart',
            display_name='cloudwatch_agent_alart'
        )
        _topic.add_subscription(aws_sns_subscriptions.EmailSubscription(
            'yagita.takashi@gmail.com'))

        _alarm = aws_cloudwatch.Alarm(
            self,
            'Alarm',
            metric=_metric,
            threshold=2,
            comparison_operator=aws_cloudwatch.ComparisonOperator.GREATER_THAN_OR_EQUAL_TO_THRESHOLD,
            evaluation_periods=1,
            actions_enabled=True
        )
        _alarm.add_alarm_action(aws_cloudwatch_actions.SnsAction(_topic))
