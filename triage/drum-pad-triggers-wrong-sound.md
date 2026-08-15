---
devices: [alesis/nitro-max, ableton/live-12]
---

# A drum pad triggers the wrong sound

also: the wrong drum plays; the snare pad plays a tom; the pads are mapped wrong

## The pad sends a note the Drum Rack does not answer on
check: the pad's MIDI note number is not the Receive note of the chain it should play
fix: alesis/nitro-max §5.2 "Pad MIDI Note Numbers"
fix: ableton/live-12 §24.6 "Drum Racks"

## The module is in General MIDI mode
check: the display shows GM, and Channel 10 plays General MIDI percussion rather than the
kit you saved
fix: alesis/nitro-max §4.4 "MIDI Settings"

## The module and the track disagree about the channel
check: the module sends on Channel 10 while the track is listening on another channel
fix: alesis/nitro-max §4.4 "MIDI Settings"
fix: ableton/live-12 §17.3.1 "MIDI Port Inputs and Outputs"

## Otherwise
One pad wrong is a mapping; every pad wrong by the same interval is the kit, and the whole
kit playing the wrong instrument is the module's own sound selection rather than anything
in the software.
