import json 
from pathlib import Path
from typing import Dict
import torch
from ..config import Config
from ..utils import build_model
from ..tokenizer import Tokenizer
from wasabi import msg



class HFModelHelper:
    
    hf_architecture: str
    
    def __init__(self, checkpoint_dir: str):
        self.checkpoint_dir = Path(checkpoint_dir)
        with open(self.checkpoint_dir / "config.json", "r") as f:
            self.hf_config = json.load(f)
        assert self.hf_architecture in self.hf_config['architectures'], f'Only support {self.hf_architecture} model, current model is {self.hf_config["architectures"]}'
        try:
            self.tokenizer = Tokenizer(self.checkpoint_dir)
        except Exception:
            msg.warn("No tokenizer found")
            self.tokenizer = None
    
    @property
    def weight_map(self) -> Dict:
        raise NotImplementedError("Method not implemented")
    
    @property
    def osc_config(self) -> Config:
        raise NotImplementedError("Method not implemented")
    
    def convert_checkpoint(self, save_dir: str):
        """将huggingface模型转换为osc格式模型

        Args:
            save_dir (str): 保存目录
        """
        pytorch_model = Path(self.checkpoint_dir) / 'pytorch_model.bin'
        pytorch_idx_file = Path(self.checkpoint_dir) / 'pytorch_model.bin.index.json'
        if pytorch_model.exists() or pytorch_idx_file.exists():
            sd = self.convert_pytorch_format()
        safetensors_model = Path(self.checkpoint_dir) / 'model.safetensors'
        safetensors_idx_file = Path(self.checkpoint_dir) / 'model.safetensors.index.json'
        if safetensors_model.exists() or safetensors_idx_file.exists():
            sd = self.convert_safetensor_format()
        if not pytorch_model.exists() and not safetensors_model.exists() and not pytorch_idx_file.exists() and not safetensors_idx_file.exists():
            raise FileNotFoundError("No pytorch model file found")
        out_dir = Path(save_dir)
        if not out_dir.exists():
            out_dir.mkdir(parents=True)
        torch.save(sd, out_dir / 'osc_model.pth')
        self.osc_config.to_disk(out_dir / 'config.cfg')
        if self.tokenizer:
            self.tokenizer.save(out_dir)
    
    def convert_pytorch_format(self):
        sd = {}
        wmap = self.weight_map
        index_file = self.checkpoint_dir / 'pytorch_model.bin.index.json'
        if index_file.exists():
            with open(index_file, 'r') as f:
                index = json.load(f)
            files = [self.checkpoint_dir / file  for file in set(index['weight_map'].values())]
        else:
            files = [self.checkpoint_dir / 'pytorch_model.bin']
        assert len(files) > 0, 'No pytorch model file found'
        for file in files:
            weights = torch.load(str(file), map_location='cpu', weights_only=True, mmap=True)
            for key in weights:
                if key not in wmap:
                    continue
                sd[wmap[key]] = weights[key]
        return sd
        
    def convert_safetensor_format(self):
        sd = {}
        wmap = self.weight_map
        index_file = self.checkpoint_dir / 'model.safetensors.index.json'
        if index_file.exists():
            with open(index_file, 'r') as f:
                index = json.load(f)
            files = [self.checkpoint_dir / file  for file in set(index['weight_map'].values())]
        else:
            files = [self.checkpoint_dir / 'model.safetensors']
        assert len(files) > 0, 'No pytorch model file found'
        try:
            from safetensors import safe_open
        except Exception:
            raise ImportError("Please install safetensors first, run `pip install safetensors`")
        for file in files:
            with safe_open(file, framework='pt') as f:
                for key in f.keys():
                    if key not in wmap:
                        continue
                    sd[wmap[key]] = f.get_tensor(key)
        return sd
        
    def load_checkpoint(self, checkpoint_name: str = 'osc_model.pth', device: str = 'cpu'):
        model = build_model(config=self.osc_config)
        model.load_state_dict(torch.load(str(self.checkpoint_dir / checkpoint_name), mmap=True, weights_only=True), assign=True)
        model.to(device)
        return model.eval()