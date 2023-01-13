"""An AWS Python Pulumi program"""
# https://github.com/pulumi/examples/tree/master/aws-py-ec2-provisioners
# https://www.pulumi.com/registry/packages/aws/how-to-guides/ec2-webserver/

# Generate and set the key via:
# ssh-keygen -f rsa
# pulumi config set publicKeyPath rsa.pub
# pulumi config set privateKeyPath wordpress-keypair

# Connect via SSH:
# ssh -i "rsa" ec2-user@ec2-34-245-163-159.eu-west-1.compute.amazonaws.com

import pulumi
import pulumi_aws as aws
import pulumi_command as command
import base64
import checksumdir
from pathlib import Path

config = pulumi.Config()

# If keyName is provided, an existing KeyPair is used, else if publicKey is provided a new KeyPair
# derived from the publicKey is created.
# key_name = config.get('keyName')
# public_key = config.get('publicKey')

publicKeyPath = config.require('publicKeyPath')
privateKeyPath = config.require('privateKeyPath')

publicKey = Path(publicKeyPath).read_text()
privateKey = pulumi.Output.secret(Path(privateKeyPath).read_text())

keyPair = aws.ec2.KeyPair('key', public_key=publicKey)

size = 't2.micro'
ami = aws.ec2.get_ami(most_recent="true",
        owners=["137112412989"],
        filters=[{"name":"name","values":["amzn2-ami-hvm-*"]}])

# Create a new security group that permits SSH and web access.
secgrp = aws.ec2.SecurityGroup('secgrp',
        description='SSH and Webserver access',
        ingress=[
            aws.ec2.SecurityGroupIngressArgs(protocol='tcp', from_port=22, to_port=22, cidr_blocks=['0.0.0.0/0']),
            aws.ec2.SecurityGroupIngressArgs(protocol='tcp', from_port=80, to_port=80, cidr_blocks=['0.0.0.0/0']),
            aws.ec2.SecurityGroupIngressArgs(protocol='tcp', from_port=443, to_port=443, cidr_blocks=['0.0.0.0/0']),
            ],
        egress=[
            aws.ec2.SecurityGroupIngressArgs(protocol='-1', from_port=0, to_port=0, cidr_blocks=['0.0.0.0/0']),
            ],
        )

# Provison the EC2 machine
server = aws.ec2.Instance('ec2-example',
        instance_type=size,
        key_name=keyPair.id,
        vpc_security_group_ids=[secgrp.id], # reference security group from above
        ami=ami.id)

# Not completely sure I still need this
connection = command.remote.ConnectionArgs(
    host=server.public_ip,
    user='ec2-user',
    private_key=privateKey,
)

# Hash the dirs contents to determine if an update is needed.
# TODO: This just triggers everytime. write it out to a file and compare or something
checksum = checksumdir.dirhash('.', 'md5')

# Play the Ansible playbook
play_ansible_playbook_cmd = command.local.Command("playAnsiblePlaybookCmd",
    create=server.public_ip.apply(lambda public_ip: f"""\
            ANSIBLE_HOST_KEY_CHECKING=False ANSIBLE_PYTHON_INTERPRETER=auto_silent ansible-playbook \
            -u ec2-user \
            -i '{public_ip},' \
            --private-key {privateKeyPath} \
            nginx-playbook.yml"""),
    triggers=[checksum],
)

pulumi.export('publicIp', server.public_ip)
pulumi.export('publicHostName', server.public_dns)
