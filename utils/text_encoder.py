import logging
import warnings
warnings.filterwarnings("ignore", message="pkg_resources is deprecated")
import numpy as np
import open_clip
import torch
import torch.nn.functional as F
import timm
from transformers import XLMRobertaTokenizer
import config
from unilm.beit3.modeling_finetune import beit3_large_patch16_384_retrieval
logger = logging.getLogger(__name__)

class CLIPTextEncoder:
    def __init__(self, device: str = "cuda"):
        self.device = device
        logger.info(f"Loading model '{config.CLIP_MODEL_NAME}' to device '{self.device}'...")
        self.model, _, _ = open_clip.create_model_and_transforms(
            config.CLIP_MODEL_NAME,
            pretrained=config.CLIP_PRETRAINED
        )
        
        del self.model.visual
        
        self.model = self.model.to(self.device)
        self.model.eval()
        self.tokenizer = open_clip.get_tokenizer(config.CLIP_MODEL_NAME)

        logger.info("CLIPTextEncoder initialized successfully.")

    def encode(self, query: str):
        text_inputs = self.tokenizer([query]).to(self.device)

        with torch.no_grad():
            text_features = self.model.encode_text(text_inputs)
            if self.device  == "cuda":
                text_features = text_features.cpu()
            return F.normalize(text_features, p=2, dim=-1).detach().numpy().astype(np.float32)

class BEIT3TextEncoder:
    def __init__(self, device: str = "cuda"):
        self.device = device
        logger.info(f"Loading {config.BEIT3_MODEL_NAME} model to device '{self.device}'...")
        self.model = timm.create_model(config.BEIT3_MODEL_NAME, pretrained=False)
        checkpoint = torch.load(config.BEIT3_MODEL_PATH, map_location=self.device)
        self.model.load_state_dict(checkpoint["model"], strict=False)
        self.model = self.model.to(self.device)
        self.model.eval()

        self.tokenizer = XLMRobertaTokenizer(config.BEIT3_TEXT_ENCODER_PATH)
        logger.info("BEIT3TextEncoder initialized successfully.")

    def encode(self, query: str):
        inputs = self.tokenizer(query, return_tensors="pt", padding=True)
        input_ids = inputs["input_ids"].to(self.device)

        with torch.no_grad():
            text_features = self.model.forward(text_description=input_ids,
                                                only_infer=True)[-1]
            
            if self.device == "cuda":
                text_features = text_features.cpu()
            return F.normalize(text_features, p=2, dim=-1).detach().numpy().astype(np.float32)
        
if __name__ == "__main__":
    encoder = CLIPTextEncoder(device="cuda" if torch.cuda.is_available() else "cpu")
    sample_text = "A person riding a horse on a beach."
    features = encoder.encode(sample_text)
    print("Features:", features)