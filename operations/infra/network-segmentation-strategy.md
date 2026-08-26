# Network Segmentation Strategy

## Overview

Network segmentation is a critical security practice that divides network infrastructure into smaller, isolated segments to limit lateral movement and contain potential breaches. This strategy involves designing secure VPC architectures with proper isolation between different network zones, implementing robust access controls, and leveraging modern security patterns like zero-trust and service mesh technologies.

## VPC Design Principles

A well-designed Virtual Private Cloud (VPC) serves as the foundation for effective network segmentation. The typical VPC architecture includes public and private subnets distributed across multiple Availability Zones for high availability. Public subnets contain internet-facing resources like load balancers, while private subnets house application servers and databases that should never be directly accessible from the internet.

```yaml
# Example VPC configuration with proper subnet placement
resources:
  VPC:
    Type: AWS::EC2::VPC
    Properties:
      CidrBlock: 10.0.0.0/16
      EnableDnsHostnames: true
      EnableDnsSupport: true

  PublicSubnet1:
    Type: AWS::EC2::Subnet
    Properties:
      VpcId: !Ref VPC
      CidrBlock: 10.0.1.0/24
      AvailabilityZone: us-east-1a
      MapPublicIpOnLaunch: true

  PrivateSubnet1:
    Type: AWS::EC2::Subnet
    Properties:
      VpcId: !Ref VPC
      CidrBlock: 10.0.2.0/24
      AvailabilityZone: us-east-1a
      MapPublicIpOnLaunch: false
```

## Security Groups vs NACLs

Security groups act as virtual firewalls for EC2 instances and function as stateful controls, automatically allowing return traffic for established connections. Network Access Control Lists (NACLs) operate at the subnet level and are stateless, requiring explicit rules for both inbound and outbound traffic.

```yaml
# Security Group Example - Stateful, Instance-Level Protection
Resources:
  WebServerSecurityGroup:
    Type: AWS::EC2::SecurityGroup
    Properties:
      GroupDescription: Allow HTTP and HTTPS access
      VpcId: !Ref VPC
      SecurityGroupIngress:
        - IpProtocol: tcp
          FromPort: 80
          ToPort: 80
          CidrIp: 0.0.0.0/0
        - IpProtocol: tcp
          FromPort: 443
          ToPort: 443
          CidrIp: 0.0.0.0/0
      SecurityGroupEgress:
        - IpProtocol: tcp
          FromPort: 443
          ToPort: 443
          CidrIp: 0.
