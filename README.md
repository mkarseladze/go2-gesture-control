# Go2 Gesture Control

Control a Unitree Go2 with hand gestures from a laptop camera. The optional Jetson camera stream shows the robot's RealSense view beside the gesture camera and recognizes a wave for the built-in Hello action.

## Run on Ubuntu

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m unittest -v
python app.py --camera 0
```

For live control, build the SDK2 helpers after installing the Unitree C++ SDK. Update the SDK path if installed elsewhere.

```bash
sdk=/opt/unitree_robotics
for name in go2_forward read_go2_state; do
  g++ -std=c++17 -isystem "$sdk/include" -isystem "$sdk/include/ddscxx" \
    "$name.cpp" -L"$sdk/lib" -Wl,-rpath,"$sdk/lib" \
    -lunitree_sdk2 -lddscxx -lddsc -pthread -o "$name" || break
done
python app.py --camera 0 --go2 YOUR_ETHERNET_INTERFACE
```

Keep the movement area clear and have an independent stop available. Press **A** to enable control, **Space** to disable, and **Q** to exit.

## Gestures

| Gesture | Action |
| --- | --- |
| One to four upright fingers, thumb tucked | Forward, backward, left, right |
| Index finger pointing down | Sit |
| Both index fingers pointing up | Stand up |
| Finger heart | Heart |
| Thumb and pinky extended | Dance 1 |
| Open-hand wave in the Go2 camera | Hello |

Movement stops when the gesture is lost. One-shot actions disarm gesture control after being sent.

For the optional Jetson camera, run `jetson_streamer.py` on the Jetson and add `--jetson-camera JETSON_IP` on the laptop. For optional Go2 speaker playback, supply a local track with `--go2-dance-file PATH` and configure authorized WebRTC access. The speaker integration has not been verified on the physical Go2.

See [README.txt](README.txt) for additional setup notes.
