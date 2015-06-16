#!/bin/bash

SERVICE_NAME=autoregister
UPSTART_CONF_DIR=/etc/init
GROUP=`id -gn $USER`
AUTOREGISTER=`pwd`"/autoregister.py"
LOGDIR=~/logs
mkdir -p $LOGDIR
LOGFILE=${LOGDIR}/${SERVICE_NAME}.log

echo "Trying to create service \"$SERVICE_NAME\"..."
if [ -f ${UPSTART_CONF_DIR}/${SERVICE_NAME}.conf ]
then
    echo "Service with such name already exists. Change SERVICE_NAME in $0"
    exit 1
fi

if [ -z $ANDROID_HOME ] || ! [ -d $ANDROID_HOME ]
then
    echo "ERROR Set valid path to Android SDK in ANDROID_HOME environment variable"
    exit 1
fi

if [ -z $APPIUM_EXECUTABLE ] || ! [ -f $APPIUM_EXECUTABLE ]
then
    echo "ERROR Set valid path to Appium executable in APPIUM_EXECUTABLE environment variable"
    exit 1
fi

echo "hostname[localhost]:"
read GRID_HOST
if [ -z "$GRID_HOST" ]
then
    GRID_HOST=localhost
fi

sudo -E bash << EOF
echo "description \"appium-autoregister daemon\"
setuid $USER
setgid $GROUP
start on runlevel [2345]
stop on runlevel [06]

script
    export PATH=$PATH
    pkill -f autoregister.py || echo "WARN pkill exit code != 0" >> $LOGFILE 2>&1
    export APPIUM_EXECUTABLE=$APPIUM_EXECUTABLE >> $LOGFILE 2>&1
    export ANDROID_HOME=$ANDROID_HOME >> $LOGFILE 2>&1
    python3 $AUTOREGISTER --grid-host=$GRID_HOST >> $LOGFILE 2>&1
end script

respawn
respawn limit 10 90" > ${UPSTART_CONF_DIR}/${SERVICE_NAME}.conf

[ $? == 0 ] || exit 1
echo "Service \"$SERVICE_NAME\" successfully created"
EOF
