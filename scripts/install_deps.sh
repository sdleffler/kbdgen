#!/usr/bin/env bash

NDK_DL_URL=http://dl.google.com/android/repository
NDK_PATH=android-ndk-r10e
NDK_FN_LINUX=$NDK_PATH-linux-x86_64.zip

NDK_URL_LINUX=$NDK_DL_URL/$NDK_FN_LINUX
SDK_PATH=android-sdk-linux
SDK_FN_LINUX=android-sdk_r24.4.1-linux.tgz
SDK_URL_LINUX=https://dl.google.com/android/
SDK_TOOLS="tools,platform-tools,build-tools-21,extra-android-support,android-21"

ios_deps() {
	echo "Installing autotools..."
	brew install automake autoconf libtool bison

	echo "Installing ios-autotools..."
	pushd $HOME
	git clone https://github.com/bbqsrc/ios-autotools.git
	mkdir $HOME/.bin
	cp ios-autotools/{autoframework,iconfigure} $HOME/.bin
	chmod +x .bin/*
	export PATH="$PATH:$HOME/bin"
	popd
}

android_deps() {
	pushd $HOME
	wget $NDK_URL_LINUX
	wget $SDK_URL_LINUX

	echo "Installing Android NDK r10e..."
	unzip $NDK_FN_LINUX
	export NDK_HOME=$PWD/$NDK_PATH

	echo "Installing Android SDK r24.4.1..."
	unzip $SDK_FN_LINUX
	export ANDROID_HOME=$PWD/$SDK_PATH

	echo "Installing android-autotools..."
	pip install android-autotools

	$ANDROID_HOME/tools/android update sdk -u -t $SDK_TOOLS
	popd
}


# Prep OS X environment
if [[ "$TRAVIS_OS_NAME" == "osx" ]]; then
	brew update
	brew install python3 imagemagick
	virtualenv ~/venv -p python3
	source ~/venv/bin/activate
fi

case $TARGET in
	ios)
		ios_deps;;
	android)
		android_deps;;
esac
