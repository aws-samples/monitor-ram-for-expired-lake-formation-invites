"""
Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
SPDX-License-Identifier: MIT-0

This module contains functions and classes that help with interacting with DynamoDB. DynamoDB
is used to store and retrieve permissions for expired RAM shares. It hopes a snapshot before
we start revoking permissions so that those permissions can be regranted in the event of an error
occurs before doing grants.
"""

import json

from aws_lambda_powertools import Logger, Tracer

logger = Logger()
tracer = Tracer()


class DdbManager:
    """
    Class that interacts with DDB by retrieving, updating, or saving Permissions for a RAM Share.
    """

    def __init__(self, ddb_client, table_name):
        self.ddb_client = ddb_client
        self.ddb_table_name = table_name

    def get_previously_failed_accounts_for_resource_share(self) -> dict[str, str]:
        """
        Get all permissions from the DDB table.
        """
        scan_paginator = self.ddb_client.get_paginator("scan")
        permissions_from_ddb: dict[str, str] = {}

        for item_page in scan_paginator.paginate(TableName=self.ddb_table_name, Select="ALL_ATTRIBUTES"):
            for item in item_page["Items"]:
                permissions_from_ddb[item["resourceShareArn"]["S"]] = json.loads(item["aws_account"]["S"])

        logger.info(f"Retrieved {len(permissions_from_ddb)} accounts for shares from DDB: {permissions_from_ddb}")
        return permissions_from_ddb

    def add_resource_share_to_ddb(self, resource_share_arn: str, aws_account_id: str):
        """
        Add a resource share to the DDB table.
        """
        try:
            self.ddb_client.put_item(TableName=self.ddb_table_name, Item={"resourceShareArn": {"S": resource_share_arn}, "aws_account": {"S": aws_account_id}})
        except self.ddb_client.meta.client.exceptions.InternalServerError as e:
            logger.critical(f"Failed to put item in DDB to retry later! {resource_share_arn}. ")
            raise e

    def remove_resource_share_from_ddb(self, resource_share_arn: str):
        """
        Remove the resource share from the DDB table.
        """
        try:
            self.ddb_client.delete_item(TableName=self.ddb_table_name, Key={"resourceShareArn": {"S": resource_share_arn}})
        except self.ddb_client.exceptions.ResourceNotFoundException:
            # Ignore this error because it would be called from removing DDB item.
            logger.info(f"DDB Failed to find item for {resource_share_arn}. Ignoring.")
