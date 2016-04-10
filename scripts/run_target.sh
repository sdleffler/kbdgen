#!/usr/bin/env bash

CMD="python -m kbdgen"
PROJECT="examples/project.yaml"

export PATH="$PATH:$HOME/.bin:/usr/local/opt/gettext/bin"

case $TARGET in
	ios)
		$CMD -t ios -b hfst -r https://github.com/bbqsrc/tasty-imitation-keyboard $PROJECT
		;;
	android)
		$CMD -t android -b hfst -r https://github.com/bbqsrc/giella-ime $PROJECT
		;;
	*)
		$CMD -t $TARGET $PROJECT
		;;
esac
