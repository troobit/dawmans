---
devices: [ableton/live-12, focusrite/scarlett-solo]
---

# Latency when monitoring

also: I hear myself late; there is a delay when I play in; monitoring lags

## The audio buffer size is too high for tracking
check: the delay is audible while you play in, but the recording lines up on playback
fix: ableton/live-12 §39.5 "Tips for Achieving Optimal MIDI Performance"

## Direct Monitor is off on the interface
check: the Direct icon on the Scarlett is white rather than green
why: it costs nothing to try and takes the computer out of the path entirely
fix: focusrite/scarlett-solo-4g "Direct Monitor Button"

## The track's Monitor is set to In
check: the Monitor radio button shows In, so everything you play is heard through the
track's device chain rather than off the interface
fix: ableton/live-12 §17.1 "Monitoring"

## The Overall Latency adjustment has never been made
check: takes recorded with the Monitor set to Off land early or late by the same amount
every time
fix: ableton/live-12 §17.1 "Monitoring"

## Otherwise
Latency you can hear but cannot measure in a recording is the room, not the rig: a monitor
speaker three metres away is already about nine milliseconds of it.
