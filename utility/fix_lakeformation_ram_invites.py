'''
Copyright 2024 Amazon.com, Inc. or its affiliates. All Rights Reserved.

Permission is hereby granted, free of charge, to any person obtaining a copy of
this software and associated documentation files (the "Software"), to deal in
the Software without restriction, including without limitation the rights to
use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of
the Software, and to permit persons to whom the Software is furnished to do so.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS
FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR
COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER
IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN
CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.

Script Purpose:
=====================================================================================
Iterates through Lake Formation permissions to get RAM share information, and checks
if they are valid. If they are not valid, it will attempt to fix it. 

'''
# pylint: disable=logging-fstring-interpolation
#----------------------------------------------------------------------------------------
#                         Create Clients, etc
#----------------------------------------------------------------------------------------
import argparse
import logging
import time

import boto3

session = boto3.session.Session()
lf = session.client('lakeformation')
ram = session.client('ram')

logger = logging.getLogger(__name__)

ELEVEN_HOURS_IN_SECS = 11 * 60 * 60
IS_DRY_RUN = True

argParser = argparse.ArgumentParser(description='A utility that will replicate a table to another with certain information stripped from it.')
argParser.add_argument('--no-dry-run', action='store_false', help='Do not perform any actions, just print what would be done. Default: True')
argParser.add_argument("--log_level", "-l", help="log level as DEBUG, INFO, WARN, ERROR. ", default="INFO", required=False)
namespace = argParser.parse_args()

logging.basicConfig(format='%(levelname)s:%(message)s', level=namespace.log_level)
IS_DRY_RUN = namespace.no_dry_run

logger.info(f"Starting script with Dry Run: {IS_DRY_RUN}")

def get_account_id(principal: list[str]) -> str:
    '''
    Returns account id from an ARN or account id.
    '''
    # if its a direct share, get the account id
    if principal.startswith('arn:aws:iam::'):
        return principal.split(':')[4]
    # else its an account id.
    if principal.isdigit() and len(principal) == 12:
        return principal
    raise ValueError(f"Invalid principal: {principal}")

perms : dict = lf.list_permissions()
timeout_timestamp = int(time.time()) - ELEVEN_HOURS_IN_SECS

while perms.get("NextToken") is not None:

    for permission in perms["PrincipalResourcePermissions"]:
        if 'AdditionalDetails' in permission and 'ResourceShare' in permission['AdditionalDetails']:
            resource_share_arns = permission['AdditionalDetails']['ResourceShare']
            account_id : str = get_account_id(permission['Principal']['DataLakePrincipalIdentifier'])
            # This should only loop once.
            for resource_share_arn in resource_share_arns:
                try:
                    share_associations = ram.get_resource_share_associations(resourceShareArns=[resource_share_arn], associationType='PRINCIPAL')
                    if len(share_associations['resourceShareAssociations']) != 1:
                        logger.debug(f"We should only get one Resource Share. Got 0 or more than 1 shares for {resource_share_arn}. Ignoring this share.")
                        continue

                    resource_share = share_associations['resourceShareAssociations'][0]
                    # If there aren't any associations, we'll add the association.
                    if not resource_share['associatedEntity']:
                        logger.info(f"Found resource share without principals. Associating {account_id} with {resource_share_arn}")
                        if not IS_DRY_RUN:
                            ram.associate_resource_share(resourceShareArn=resource_share_arn, principals=[account_id])
                            logger.info("Successfully assosciated Account: {account_id} with RAM share: {resource_share_arn}")
                    # If the account id's dont match, something went wrong. We'll skip it.
                    elif resource_share['associatedEntity'] != account_id:
                        logger.warning(f"Principal {account_id} does not match resource shares associated entity: {resource_share['associatedEntity']} for resource share: {resource_share_arn}. Ignoring for now.")
                    # Check if the account association failed.
                    elif resource_share['status'] == 'FAILED':
                        logger.info(f"Resource Share {resource_share_arn} is in FAILED state. Disassociating and then re-associating with principal {account_id}.")
                        if not IS_DRY_RUN:
                            ram.disassociate_resource_share(resourceShareArn=resource_share_arn, principals=[account_id])
                            ram.associate_resource_share(resourceShareArn=resource_share_arn, principals=[account_id])
                            logger.info('Successfully recreated RAM share.')
                    # Check if the RAM invite time is more than 11 hours, it will recreate the invite.
                    else:
                        invite_ts = resource_share["creationTime"].timestamp()
                        if int(timeout_timestamp) > int(invite_ts):
                            logger.info(f"Found Resource Share close to expiration or expired: {resource_share['resourceShareName']} that was created {(time.time() - invite_ts)/60.0/60.0} hours ago. )")
                            if not IS_DRY_RUN:
                                ram.disassociate_resource_share(resourceShareArn=resource_share_arn, principals=[account_id])
                                ram.associate_resource_share(resourceShareArn=resource_share_arn, principals=[account_id])
                                logger.info('Successfully recreated RAM share.')
                except ram.exceptions.UnknownResourceException as e:
                    logger.warning(f"Ram Share {resource_share_arn} doesn't exist. Ignoring for now.")

    if perms.get("NextToken") is None:
        break

    perms = lf.list_permissions(NextToken=perms.get("NextToken"))
