#!/bin/bash

SERVICE_NAME=selenium-grid
UPSTART_CONF_DIR=/etc/init
GROUP=`id -gn $USER`
SELENIUM_JAR=`pwd`"/selenium-server-standalone-2.45.0.jar"
LOGDIR=~/logs
mkdir -p $LOGDIR
LOGFILE=${LOGDIR}/${SERVICE_NAME}.log

echo "Trying to create service \"$SERVICE_NAME\"..."
if [ -f ${UPSTART_CONF_DIR}/${SERVICE_NAME}.conf ]
then
    echo "Service with such name already exists. Change SERVICE_NAME in $0"
    exit 1
fi

echo "hostname[localhost]:"
read GRID_HOST
if [ -z "$GRID_HOST" ]
then
    GRID_HOST=localhost
fi

sudo -E bash << EOF
echo "description \"selenium-grid daemon\"
setuid $USER
setgid $GROUP
start on runlevel [2345]
stop on runlevel [06]

script
    pkill -f selenium || echo "WARN pkill exit code != 0"  >> $LOGFILE 2>&1
    java -jar $SELENIUM_JAR -role hub -host $GRID_HOST >> $LOGFILE 2>&1
end script

respawn
respawn limit 10 90" > ${UPSTART_CONF_DIR}/${SERVICE_NAME}.conf

[ $? == 0 ] || exit 1
echo "Service \"$SERVICE_NAME\" successfully created"
EOF
