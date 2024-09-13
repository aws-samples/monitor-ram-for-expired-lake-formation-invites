"""
Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
SPDX-License-Identifier: MIT-0

This module contains RAM related classes and functions.
"""

import time

from aws_lambda_powertools import Logger, Tracer

logger = Logger()
tracer = Tracer()


class RamManager:  # pylint: disable=too-few-public-methods
    """
    This class interacts with AWS RAM.
    """

    def __init__(self, ram_client, timeout_in_secs: int, dry_run: bool):
        self.ram_client = ram_client
        self.timeout_timestamp = int(time.time()) - timeout_in_secs
        self.dry_run = dry_run
        logger.info(f"Using {timeout_in_secs} seconds as the timeout for RAM invitations")

    def get_new_expired_ram_invitations(self) -> dict[str, list[dict]]:
        """
        Get a list of share share arnsa that have associating resources that are still in
        associating state.
        """
        expired_invitations: dict[str, list[str]] = {}
        paginator = self.ram_client.get_paginator("get_resource_share_associations")
        page_iterator = paginator.paginate(associationType="PRINCIPAL", associationStatus="ASSOCIATING")

        logger.info(f"Looking for invitations that are older than {self.timeout_timestamp} seconds in epoch")

        for page in page_iterator:
            for invitation in page["resourceShareAssociations"]:
                invite_ts = invitation["creationTime"].timestamp()
                if invitation["resourceShareName"].startswith("LakeFormation-") and int(self.timeout_timestamp) > int(invite_ts):
                    logger.info(f"Found Invitation for expiration: {invitation['resourceShareName']} that was created at {invite_ts} epoch ({time.time() - invite_ts} )")
                    expired_invitations[invitation["resourceShareArn"]] = invitation["associatedEntity"]

        return expired_invitations

    def deassociate_account_from_ram_share(self, resource_share_arn: str, aws_account_id: str):
        """
        Deassociate the given account from the given RAM share.
        """
        if self.dry_run:
            self.ram_client.disassociate_resource_share(resourceShareArn=resource_share_arn, principals=[aws_account_id])
        else:
            logger.info(f"[Dry Run] Would have disassociated {aws_account_id} from {resource_share_arn}")

    def associate_account_with_ram_share(self, resource_share_arn: str, aws_account_id: str):
        """
        Associate the given account with the given RAM share.
        """
        if self.dry_run:
            self.ram_client.associate_resource_share(resourceShareArn=resource_share_arn, principals=[aws_account_id])
        else:
            logger.info(f"[Dry Run] Would have associated {aws_account_id} with {resource_share_arn}")
