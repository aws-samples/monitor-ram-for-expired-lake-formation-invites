"""
This module is called by the AWS Lambda service. 
This code will look through all RAM invitations that exist in this account and will 
identify which invitations have expired. If it finds an expired invitation, it will 
revoke the corresponding Lake Formation permissions, and recreate it, to generate a new RAM 
invitation.
This Lambda function is designed to be called periodically, for example once a day, or a few times
a day.
"""

import boto3
import botocore
from aws_lambda_powertools import Logger, Tracer

from lf_stale_ram_invite_monitor.ddb_manager import DdbManager
from lf_stale_ram_invite_monitor.ram_manager import RamManager

tracer = Tracer()
logger = Logger()

ddb_client = boto3.client("dynamodb")
ram_client = boto3.client("ram")

ELEVEN_HOURS_IN_SECS = 11 * 60 * 60


@tracer.capture_lambda_handler
def lambda_handler(event, _context):
    """
    Main Lambda handler.
    """

    try:
        logger.info("Getting expired RAM invitations...")
        timeout_in_seconds: int = event["ram_timeout_in_seconds"] if "ram_timeout_in_seconds" in event else ELEVEN_HOURS_IN_SECS
        dry_run = event["dry_run"] if "dry_run" in event else True

        ram_manager = RamManager(ram_client, timeout_in_seconds, dry_run)
        ddb_manager = DdbManager(ddb_client, event["ddb_table_name"])

        # Get all expired RAM shares.
        expired_ram_shares: dict[str, str] = ram_manager.get_new_expired_ram_invitations()

        previously_failed_accounts: dict[str, str] = ddb_manager.get_previously_failed_accounts_for_resource_share()
        expired_ram_shares.update(previously_failed_accounts)

        # If there are no expired RAM shares, return.
        if not expired_ram_shares:
            logger.info("No expired RAM shares found.")
            return {
                "message": "No expired RAM shares found.",
                "recreated_count": 0,
                "failed_count": 0,
            }

        refreshed_ram_shares: int = 0
        failed_ram_shares_count: int = 0

        for resource_share_arn, aws_account_id in expired_ram_shares.items():
            try:
                ram_manager.deassociate_account_from_ram_share(resource_share_arn, aws_account_id)
                try:
                    ram_manager.associate_account_with_ram_share(resource_share_arn, aws_account_id)
                    refreshed_ram_shares = refreshed_ram_shares + 1
                    if resource_share_arn in previously_failed_accounts:
                        ddb_manager.remove_resource_share_from_ddb(resource_share_arn)
                except botocore.exceptions.ClientError as e:  # pylint: disable=broad-except
                    logger.error(f"ERROR: Failed to reassociate RAM invite for {aws_account_id} for RAM Resource: {resource_share_arn}: {e}")
                    ddb_manager.add_resource_share_to_ddb(resource_share_arn, aws_account_id)
                    failed_ram_shares_count = failed_ram_shares_count + 1
            except ram_client.exceptions.UnknownResourceException:
                logger.info(f"Resource share {resource_share_arn} no longer exists. Removing from DDB.")
                if resource_share_arn in previously_failed_accounts:
                    ddb_manager.remove_resource_share_from_ddb(resource_share_arn)
            except Exception as e:  # pylint: disable=broad-except
                logger.error(f"Failed to process RAM share for account {aws_account_id} for {resource_share_arn}: {e}")
                failed_ram_shares_count = failed_ram_shares_count + 1
                continue

        # Summary
        message = f"Recreated {refreshed_ram_shares} RAM invitations. Failed = {failed_ram_shares_count}"
        logger.info(message)
        return {"message": message, "recreated_count": refreshed_ram_shares, "failed_count": failed_ram_shares_count}
    except Exception as e:  # pylint: disable=broad-except
        raise e
        logger.error(f"Unhandled error: {e}")
        return {
            "error": f"Unhandled error: {e}",
        }


if __name__ == "__main__":
    lambda_handler({"ddb_table_name": "lf_stale_ram_invite_monitor", "ram_timeout_in_seconds": 1000}, None)
