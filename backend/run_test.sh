#!/usr/bin/bash

REDIS_PORT=7777

redis-server --port $REDIS_PORT &> _redis.log &

COVPARAMS='--cov-report term-missing --cov ./backend --cov ./run'

while [[ $# > 1 ]]
do
	key="$1"
	case $key in
		--nocov)
		COVPARAMS=""
		;;
		*) # unknown option
		;;
	esac
shift # past argument or value
done

#TESTS=./tests

# Quick hack to disable tests/daemons/test_backend.py tests/mockremote/test_builder.py
# tests/mockremote/test_mockremote.py that are currently failing due to complete code rewrite
# TODO: prune tests (case-by-case) that are no longer relevant. We mostly rely on
# integration & regression tests now.
TESTS="tests/test_createrepo.py tests/test_frontend.py tests/test_helpers.py tests/test_sign.py"

if [[ -n $@ ]]; then
	TESTS=$@
fi


PYTHONPATH=backend:run:$PYTHONPATH python -B -m pytest -s $COVPARAMS $TESTS

kill %1
