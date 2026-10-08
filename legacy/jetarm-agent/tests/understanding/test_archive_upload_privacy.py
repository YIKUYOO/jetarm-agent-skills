from jetarm_demo_agent.config import Settings
from jetarm_demo_agent.understanding.openai_vision_client import OpenAIVisionClient


def test_archive_vision_uses_inline_image_without_proxy():
    class NoNetworkClient:
        def post(self, *args, **kwargs):
            raise AssertionError("Default image conversion must not contact an upload proxy")

    vision = OpenAIVisionClient(Settings(account_file="nonexistent-private-account.txt", openai_api_key="example-vision-key"))
    image_url = vision._upload_frame(NoNetworkClient(), {"image_base64": "dGVzdA==", "media_type": "image/jpeg"})
    assert image_url == "data:image/jpeg;base64,dGVzdA=="


def test_explicit_upload_uses_separate_credential():
    calls = []
    class Client:
        def post(self, url, **kwargs):
            calls.append((url, kwargs))
            class Response:
                def raise_for_status(self):
                    pass
                def json(self):
                    return {"url": "https://images.example.invalid/frame.jpg"}
            return Response()

    vision = OpenAIVisionClient(Settings(account_file="nonexistent-private-account.txt",
        openai_api_key="example-vision-key", vision_upload_url="https://upload.example.invalid",
        vision_upload_api_key="example-upload-key"))
    assert vision._upload_frame(Client(), {"image_base64": "dGVzdA=="}).endswith("frame.jpg")
    assert calls[0][0] == "https://upload.example.invalid"
    assert calls[0][1]["headers"] == {"Authorization": "Bearer example-upload-key"}
    assert "example-vision-key" not in repr(calls)
