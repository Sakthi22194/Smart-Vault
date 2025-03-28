import boto3
import datetime

def lambda_handler(event, context):
    ec2 = boto3.client('ec2')
    sns = boto3.client('sns')
    cloudwatch = boto3.client('cloudwatch')  
    sns_topic_arn = 'arn:aws:sns:us-east-1:841162714455:BackupAlerts'
    retention_days = 7
    
    try:
        instances = ec2.describe_instances(Filters=[
            {'Name': 'tag:Backup', 'Values': ['True']}
        ])
        
        for reservation in instances['Reservations']:
            for instance in reservation['Instances']:
                instance_id = instance['InstanceId']
                print(f"Creating snapshot for instance: {instance_id}")
                
                volumes = ec2.describe_volumes(Filters=[
                    {'Name': 'attachment.instance-id', 'Values': [instance_id]}
                ])
                
                for volume in volumes['Volumes']:
                    volume_id = volume['VolumeId']
                    description = f"SmartVault backup for {instance_id} at {datetime.datetime.now()}"
                    
                    snapshot = ec2.create_snapshot(
                        VolumeId=volume_id,
                        Description=description
                    )
                    
                    ec2.create_tags(
                        Resources=[snapshot['SnapshotId']],
                        Tags=[
                            {'Key': 'Name', 'Value': f"SmartVault-{instance_id}"},
                            {'Key': 'CreatedAt', 'Value': str(datetime.datetime.now())},
                            {'Key': 'Environment', 'Value': 'Production'}
                        ]
                    )
        
        snapshots = ec2.describe_snapshots(OwnerIds=['self'], Filters=[
            {'Name': 'tag:Name', 'Values': ['SmartVault-*']}
        ])
        
        snapshot_count = len(snapshots['Snapshots'])
        total_size_gb = sum(snapshot['VolumeSize'] for snapshot in snapshots['Snapshots'])
        
        cloudwatch.put_metric_data(
            Namespace='SmartVaultMetrics',
            MetricData=[
                {
                    'MetricName': 'SnapshotCount',
                    'Value': snapshot_count,
                    'Unit': 'Count'
                },
                {
                    'MetricName': 'SnapshotStorageSize',
                    'Value': total_size_gb,
                    'Unit': 'Gigabytes'
                }
            ]
        )
        
        for snapshot in snapshots['Snapshots']:
            created_at_str = snapshot['StartTime'].strftime('%Y-%m-%d')
            created_at = datetime.datetime.strptime(created_at_str, '%Y-%m-%d')
            created_at = created_at.replace(tzinfo=datetime.timezone.utc)
            now = datetime.datetime.now(datetime.timezone.utc)
            if (now - created_at).days > retention_days:
                print(f"Deleting snapshot: {snapshot['SnapshotId']}")
                ec2.delete_snapshot(SnapshotId=snapshot['SnapshotId'])
        
        sns.publish(
            TopicArn=sns_topic_arn,
            Message='Backup process completed successfully',
            Subject='Backup Success'
        )
        
        return {
            'statusCode': 200,
            'body': 'Backup process completed'
        }
    
    except Exception as e:
        sns.publish(
            TopicArn=sns_topic_arn,
            Message=f'Backup process failed: {str(e)}',
            Subject='Backup Failure'
        )
        raise e