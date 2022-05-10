#!/usr/bin/env python3
import os
import aws_cdk as cdk
from _stacks.main_stack import MainStack


app = cdk.App()
MainStack(app, "SsmRunCommandToCloudWatchStack")

app.synth()
