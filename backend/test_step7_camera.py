"""Step 7 Camera Reception Endpoint Tests."""

import io
from PIL import Image
from fastapi.testclient import TestClient
from main import app
from websocket_manager import get_ws_manager


def _create_sample_image(format="JPEG", size=(320, 240)):
    buf = io.BytesIO()
    img = Image.new("RGB", size, color=(73, 109, 137))
    img.save(buf, format=format)
    return buf.getvalue()


def test_camera_reception():
    client = TestClient(app)
    ws_mgr = get_ws_manager()

    # 1. Register a test vehicle in the manager
    fake_ws = object()
    ws_mgr.add_vehicle("veh_cam_1", fake_ws)

    # 2. Upload valid JPEG image
    jpeg_bytes = _create_sample_image(format="JPEG")
    resp = client.post(
        "/api/camera/frame/veh_cam_1",
        files={"file": ("frame.jpg", jpeg_bytes, "image/jpeg")},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["accepted"] is True
    assert data["vehicle_id"] == "veh_cam_1"
    print("PASS: Valid JPEG frame accepted")

    # 3. Upload valid PNG image
    png_bytes = _create_sample_image(format="PNG")
    resp_png = client.post(
        "/api/camera/frame/veh_cam_1",
        files={"file": ("frame.png", png_bytes, "image/png")},
    )
    assert resp_png.status_code == 200
    print("PASS: Valid PNG frame accepted")

    # 4. Unknown vehicle -> 404
    resp_unknown = client.post(
        "/api/camera/frame/non_existent_vehicle",
        files={"file": ("frame.jpg", jpeg_bytes, "image/jpeg")},
    )
    assert resp_unknown.status_code == 404
    print("PASS: Unknown vehicle rejected with 404")

    # 5. Unsupported file format (e.g. text or pdf) -> 415
    resp_bad_fmt = client.post(
        "/api/camera/frame/veh_cam_1",
        files={"file": ("script.py", b"# plain python script content text\n" * 10, "text/plain")},
    )
    assert resp_bad_fmt.status_code == 415
    print("PASS: Unsupported file rejected with 415")

    # 6. Corrupt image file (starts with JPEG magic but body truncated) -> 400
    corrupt_bytes = b"\xff\xd8\xff\xe0" + b"\x00" * 200
    resp_corrupt = client.post(
        "/api/camera/frame/veh_cam_1",
        files={"file": ("corrupt.jpg", corrupt_bytes, "image/jpeg")},
    )
    assert resp_corrupt.status_code == 400
    print("PASS: Corrupted image rejected with 400")

    # 7. Payload too small (< 100 bytes) -> 400
    resp_small = client.post(
        "/api/camera/frame/veh_cam_1",
        files={"file": ("empty.jpg", b"small", "image/jpeg")},
    )
    assert resp_small.status_code == 400
    print("PASS: Too-small payload rejected with 400")

    # Clean up
    ws_mgr.remove_vehicle("veh_cam_1", fake_ws)


if __name__ == "__main__":
    test_camera_reception()
    print("STEP 7 Camera reception tests PASSED successfully!")
