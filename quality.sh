#!/bin/bash

SCRIPT_DIR=$( cd -- "$( dirname -- "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )

poetry export --without-hashes --format=requirements.txt > src/requirements.txt
poetry export --without-hashes --format=requirements.txt --with=dev > tests/requirements.txt

if [[ -z "${SKIP_CF_CHECKS}" ]]; then

    OUT=$(sam validate --lint 2>&1)
    RET=$?
    if [ $RET -ne 0 ]; then
        echo "Invalid CloudFormation template detected by SAM (${RET})." >&2
        echo "${OUT}" >&2
        exit 1
    fi

    OUT=$(cfn-lint "${SCRIPT_DIR}/template.yaml" 2>&1)
    RET=$?
    if [ $RET -ne 0 ]; then
        echo "Invalid CloudFormation template detected by cfn-lint (${RET})." >&2
        echo "${OUT}" >&2
        exit 1
    fi

    OUT=$(cfn_nag "${SCRIPT_DIR}/template.yaml" 2>&1)
    RET=$?
    if [ $RET -ne 0 ]; then
        echo "Invalid CloudFormation template detected by cfn_nag (${RET})." >&2
        echo "${OUT}" >&2
        exit 1
    fi

    # Run checkov checks
    OUT=$(checkov --quiet -f "${SCRIPT_DIR}/template.yaml" --framework cloudformation 2>&1)
    RET=$?
    if [ $RET -ne 0 ]; then
        echo "Invalid CloudFormation template detected by checkov (${RET})." >&2
        echo "${OUT}" >&2
        exit 1
    fi

fi

if [[ -z "${SKIP_PY_CHECKS}" ]]; then

    # Run isort checks
    OUT=$(poetry run isort --check --diff src tests 2>&1)
    RET=$?
    if [ $RET -ne 0 ]; then
        echo "Invalid Python code detected by isort (${RET})." >&2
        echo "${OUT}" >&2
        exit 1
    fi

    # Run pylint checks
    OUT=$(poetry run pylint src tests 2>&1)
    RET=$?
    if [ $RET -ne 0 ]; then
        echo "Invalid Python code detected by pylint (${RET})." >&2
        echo "${OUT}" >&2
        exit 1
    fi

    # Run black checks
    OUT=$(poetry run black --check --diff src tests 2>&1)
    RET=$?
    if [ $RET -ne 0 ]; then
        echo "Invalid Python code detected by black (${RET})." >&2
        echo "${OUT}" >&2
        exit 1
    fi

    # Run bandit checks
    OUT=$(poetry run bandit -c pyproject.toml -r src tests 2>&1)
    RET=$?
    if [ $RET -ne 0 ]; then
        echo "Invalid Python code detected by bandit (${RET})." >&2
        echo "${OUT}" >&2
        exit 1
    fi

fi
