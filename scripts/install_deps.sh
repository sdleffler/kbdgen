#!/usr/bin/env bash

NDK_DL_URL=http://dl.google.com/android/repository
NDK_PATH=android-ndk-r10e
NDK_FN_LINUX=$NDK_PATH-linux-x86_64.zip
NDK_URL_LINUX=$NDK_DL_URL/$NDK_FN_LINUX

SDK_PATH=android-sdk-linux
SDK_FN_LINUX=android-sdk_r24.4.1-linux.tgz
SDK_URL_LINUX=https://dl.google.com/android/$SDK_FN_LINUX
SDK_TOOLS="tools,platform-tools,android-23,build-tools-23.0.3,extra-android-support"

libtool_build() {
	pushd $HOME
	sudo apt-get build-dep -y libtool

	wget https://launchpad.net/ubuntu/+archive/primary/+files/libtool_2.4.6.orig.tar.xz
	wget https://launchpad.net/ubuntu/+archive/primary/+files/libtool_2.4.6-0.1.debian.tar.xz

	tar xf libtool_2.4.6.orig.tar.xz
	pushd ./libtool-2.4.6
	tar xf ../libtool_2.4.6-0.1.debian.tar.xz

	export DEB_BUILD_OPTIONS="nocheck"
	dpkg-buildpackage -d -us -uc
	sudo dpkg -i ../*.deb
	sudo apt-get install -yf
	popd
	popd
}

yes_hack() {
	sleep 5 && while [ 1 ]; do sleep 1; echo y; done
}

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
	libtool_build

	pushd $HOME
	wget $NDK_URL_LINUX
	wget $SDK_URL_LINUX

	echo "Installing Android NDK r10e..."
	unzip -q $NDK_FN_LINUX
	export NDK_HOME=$PWD/$NDK_PATH

	echo "Installing Android SDK r24.4.1..."
	tar xf $SDK_FN_LINUX
	export ANDROID_HOME=$PWD/$SDK_PATH

	echo "Installing android-autotools..."
	git clone https://github.com/bbqsrc/android-autotools.git
	pip install ./android-autotools

	sudo add-apt-repository "deb http://us.archive.ubuntu.com/ubuntu/ trusty-backports main restricted universe multiverse"
	sudo apt-get update
	sudo apt-get install -y swig3.0
	ln -s /usr/bin/swig3.0 $HOME/.bin/swig

	yes_hack | $ANDROID_HOME/tools/android update sdk -u -a -t $SDK_TOOLS
	popd
}


# Prep OS X environment
if [[ "$TRAVIS_OS_NAME" == "osx" ]]; then
	brew update
	brew install python3 imagemagick gettext
	pip3 install virtualenv
	virtualenv ~/venv -p python3
	source ~/venv/bin/activate
	pip install -U pip
fi

case $TARGET in
	ios)
		ios_deps;;
	android)
		android_deps;;
esac
