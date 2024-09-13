"""
Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
SPDX-License-Identifier: MIT-0

Tests for the main.py file. 
"""

import os
import time
import unittest
import datetime

import boto3
import botocore
from moto import mock_aws
from unittest.mock import patch

ACCOUNT_ID = "111111111111"
REGION = "us-east-1"
DB_NAME = "test_db"
USER_NAME = "test-user"
ROLE_NAME = "test-role"

DDB_TABLE_NAME = "test-ddb-table"
FIVE_MINS_AGO = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(minutes=5)

# Original botocore _make_api_call function
orig = botocore.client.BaseClient._make_api_call  # pylint: disable=protected-access


# Mocked botocore _make_api_call function
def mock_make_api_call(self, operation_name, kwarg):
    if operation_name == "GetResourceShareAssociations":
        return {
            "resourceShareAssociations": [
                {
                    "resourceShareArn": "arn:aws:ram:us-east-1:123456789012:resource-share/4af299d5-debf-482e-9e4f-d02aef7364ef",
                    "resourceShareName": "LakeFormation-V4-ACTJVKOTWF",
                    "associatedEntity": ACCOUNT_ID,
                    "associationType": "PRINCIPAL",
                    "status": "ASSOCIATING",
                    "creationTime": FIVE_MINS_AGO,
                    "lastUpdatedTime": FIVE_MINS_AGO,
                    "external": True,
                }
            ]
        }
    if operation_name == "AssociateResourceShare":
        return {
            "resourceShareAssociations": [
                {
                    "resourceShareArn": "arn:aws:ram:us-east-1:123456789012:resource-share/4af299d5-debf-482e-9e4f-d02aef7364ef",
                    "resourceShareName": "LakeFormation-V4-ACTJVKOTWF",
                    "associatedEntity": ACCOUNT_ID,
                    "associationType": "PRINCIPAL",
                    "status": "ASSOCIATING",
                    "creationTime": FIVE_MINS_AGO,
                    "lastUpdatedTime": FIVE_MINS_AGO,
                    "external": True,
                }
            ]
        }

    if operation_name == "DisassociateResourceShare":
        return {
            "resourceShareAssociations": [
                {
                    "resourceShareArn": "arn:aws:ram:us-east-1:123456789012:resource-share/4af299d5-debf-482e-9e4f-d02aef7364ef",
                    "resourceShareName": "LakeFormation-V4-ACTJVKOTWF",
                    "associationType": "PRINCIPAL",
                    "status": "ASSOCIATING",
                    # datetime 5 mins ago utc
                    "creationTime": FIVE_MINS_AGO,
                    "lastUpdatedTime": FIVE_MINS_AGO,
                    "external": True,
                }
            ]
        }
    # If we don't want to patch the API call
    return orig(self, operation_name, kwarg)


@mock_aws
class TestProcessFileHandler(unittest.TestCase):
    """
    Test the process_file lambda handler
    """

    def setUp(self):
        self.region_name = REGION

        # Set generic environment variables
        os.environ["AWS_ACCESS_KEY_ID"] = "test"
        os.environ["AWS_SECRET_ACCESS_KEY"] = "test"  # nosec B105:hardcoded_password_string
        os.environ["AWS_SESSION_TOKEN"] = "test"  # nosec B105:hardcoded_password_string
        os.environ["AWS_DEFAULT_REGION"] = self.region_name
        os.environ["MOTO_ACCOUNT_ID"] = ACCOUNT_ID

        self.ram_client = boto3.client("ram")
        self.ddb_client = boto3.client("dynamodb")

        self.ddb_client.create_table(TableName=DDB_TABLE_NAME, AttributeDefinitions=[{"AttributeName": "resourceShareArn", "AttributeType": "S"}], KeySchema=[{"AttributeName": "resourceShareArn", "KeyType": "HASH"}], ProvisionedThroughput={"ReadCapacityUnits": 5, "WriteCapacityUnits": 5})

    def tearDown(self):
        """
        Clean up test resources
        """
        self.ddb_client.delete_table(TableName=DDB_TABLE_NAME)

    def test_ram_succeeds(self):
        """
        Tests the lambda handler with an unsupported event.
        """
        # pylint: disable=unused-variable
        event = {"ddb_table_name": DDB_TABLE_NAME, "ram_timeout_in_seconds": 1}  # 6 mins

        from lf_stale_ram_invite_monitor.lambda_handler import lambda_handler  # pylint: disable=import-outside-toplevel

        with patch("botocore.client.BaseClient._make_api_call", new=mock_make_api_call):
            print("Starting lambda")
            result = lambda_handler(event, None)
            self.assertEqual(result["recreated_count"], 1)
            self.assertEqual(result["failed_count"], 0)


if __name__ == "__main__":
    unittest.main()
