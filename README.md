# Costs

This is a cost estimate given we deploy two installations of Odoo (main and
branch), two test rigs, we deploy everything in eu-central-1 region (just for sake of
making the calculations simpler), we deploy it with the default settings, and it runs at
its minimal scale.

Such setup is going to cost us roughly ~$600 a month.

The estimate does not include data storage, data transfer, and I/O operations costs.

Please be informed, that those costs are applied *even when the setup runs  dry* without
any traffic coming through.

The estimate does not include taxes.

See [the details](https://calculator.aws/#/estimate?id=b875c67d475d801e91d45d1cf270f368f323a78d) on AWS Price Calculator.

# Deployment

1. Use ```a_global-odoo.yaml``` template to deploy CloudFormation stack in the main region.
The default parameter values are all good, no need to change them. The step completes in 10 minutes or so. Make note of the stack's outputs, you will need the values later on.

1. Initialize the database by running the command you find in the above as ```InitDbCommandLine``` output.

1. Update the stack changing ```OperationMode``` to ```run normally```. (By this moment it was ```deploying```.) The step completes in 3 minutes or so. Again make note of the stack's outputs, ```OdooUrl``` output added.

1. Open the address you find in ```OdooUrl```; user name (email) ```admin```, password ```admin```. Change admin user's password by clicking the user icon in the top-right corner, then opening ```Preferences/Account security/Change password```. Install ```CRM``` app.

1. Use ```a_global-odoo.yaml``` template to deploy CloudFormation stack in the branch region. You need to provide values for the following parameters:
```MainRegion```,
```MainVpcId```,
```RDSGlobalClusterId```,
```MainLbDnsName```,
```MainDataSyncLocationArn```.
You know the values from output of the above. The step completes in 20 minutes or so. Open stack's outputs and make a note of ```VpcPeeringConnId``` value.

1. Jump back to the main region. Update the stack providing ```VpcPeeringConnId```.

1. Jump to the branch region. Update the stack there setting ```DataSyncTaskScheduleExpression``` to ```rate(1 hour)``` and changing ```OperationMode``` to ```run normally```. The step completes in 10 minutes or so.

1. Use ```b_us-east-1-on-user-signed-in.yml``` template to deploy a CloudFormation stack in *us-east-1* region. Open stack's outputs and make a note of ```OnUserSignedInFunctionArn```.

1. Jump to the branch region. Update the stack there setting ```OnUserSignedInFunctionArn```. In stack's output find ```OdooUrl```. This is the branch's Odoo URL.

1. Open the branch URL and make sure that you are able to sign in there.

1. Stop DataSync task by jumping to the branch region, updating the stack there setting ```DataSyncTaskScheduleExpression``` to empty string.

# Suspend/resume

When suspended, the setup scales down to 0, or remove all those resources that are billed by hour, e.g. RDS database instances, load balancers, ECS containers.

When suspend it, begin with the branch region. Update the CloudFormation stack there setting ```OperationMode``` to ```suspend```. Stack update completes in 10 minutes or so. When done with suspending the brunch region, do the same in the main region.

When resume, first resume it in the main region, then in the branch region providing updated value for ```MainLbDnsName``` parameter.

After a region gets resumed, its ```OdooUrl``` changes. In case you have a test rig deployed, you need to update the rig's stack as well.

# Deploy and run the test rig(s)

1. Use ```c_test-rig.yaml``` template to deploy CloudFormation stack.
You must provide values for ```OdooUrl``` and ```OdooUserPassword``` parameters.
Also you provide ```OperatorWorkstationCidr``` to be able to connect Locust's web UI.
Typically you set it as your IP address plus */32* suffix.
Since Locust UI *is not password-protected*, it is *highly unrecommended* to it have
```OperatorWorkstationCidr``` set to *0.0.0.0/0* or similar.
After stack creation completes, make a note of ```ClusterName``` and ```ServiceName``` outputs.

1. Open ECS console and find Locust's cluster and the running task there.
We need to know its *public* IP. On this address, on ports 8089 and 8090, there are Locust web consoles. The console on port 8089 operates the *read test* (Odoo CRM's Kanban page). The another on ports 8090 operates the *write test* (adding a CRM lead).
Having to separate Locust consoles for read and write test gives you complete
freedom in regard how you shape load.

1. In order to make Locust's CPU/RAM metrics visible on the CloudWatch dashboard
which is a part of Odoo setup, open the Odoo Cloudformation stack, either in the main region or in the branch region, update the stack providing values for
```TestRigRegion```, ```TestRigClusterName``` and ```TestRigServiceName``` parameters.

When not used, it's recommended to suspend the test rig similar to how you suspend Odoo.

# Delete

1. Delete test rigs' CloudFormation stack(s).

1. Delete the branch Odoo CloudFormation stack. This may take up to 20 minutes. Delete RDS snapshot(s) if any.

1. Delete the main Odoo CloudFormation stack. This may take up to 20 minutes. Delete RDS snapshot(s) if any.

1. Delete the CloudFormation stack in us-east-1 region. (*on-user-signed-in* Lambda@Edge)
