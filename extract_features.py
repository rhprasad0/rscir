import os
import numpy as np
import torch
from PIL import Image
import open_clip
from torch.utils.data import Dataset, DataLoader
import pickle
import argparse
from torchvision.transforms import Resize, CenterCrop, Compose
from tqdm import tqdm

from utils import *

MODEL_NAME = "remoteclip"
DATASET_PATH = "./PatterNet"

class PatternNet(Dataset):
    def __init__(self, input_filename, image_transforms, root=None):
        with open(input_filename, 'r') as f:
            lines = f.readlines()
        filenames = [line.strip() for line in lines]
        self.images = [name.split(" ")[0] for name in filenames] 
        self.labels = [name.split(" ")[2] for name in filenames]
        self.image_transforms = image_transforms
        self.root = root

    def __len__(self):
        return len(self.images)

    def __getitem__(self, idx):
        if self.root is not None:
            img_path = os.path.join(self.root, str(self.images[idx]))
            url_path = f"https://ryans-website-thing-public.s3.us-west-2.amazonaws.com/PatterNet{str(self.images[idx])[1:]}"
            filename = os.path.basename(img_path)
        else:
            img_path = str(self.images[idx])
        image = self.image_transforms(Image.open(img_path).convert("RGB"))
        label = self.labels[idx]
        return image, label, url_path, filename

def save_dataset(model, dataloader, path_save):
    all_image_features, all_labels, all_image_paths = [], [], []
    embedding_tuples = []
    all_image_filenames = []
    with torch.no_grad():
        for images, labels, url_path, filename in tqdm(dataloader, desc="Processing batches"):
            images = images.cuda(non_blocking=True)
            image_features = model.encode_image(images)           
            image_features = image_features / image_features.norm(dim=-1, keepdim=True) 
            all_image_features.append(image_features)
            all_labels.extend(labels)
            all_image_paths.extend(url_path)
            all_image_filenames.extend(filename)
        
        all_image_features = torch.cat(all_image_features, dim=0).data.cpu().tolist()

        embedding_tuples.extend(zip(all_image_filenames, all_image_paths, all_image_features))
        print("embedding tuples made!")

        # dict_save = {
        #     'feats': all_image_features.data.cpu().numpy(),
        #     'labels': all_labels,
        #     'paths': all_image_paths
        # }

        directory = os.path.dirname(path_save)
        if not os.path.exists(directory):
            os.makedirs(directory)
        with open(path_save, "wb") as f:
            print('Writing pickle file...')
            pickle.dump(embedding_tuples, f)

if __name__=="__main__":
    parser = argparse.ArgumentParser(description='Extracting features from the model and saving them into pickle files.')
    parser.add_argument('--model_name', type=str, default='clip', choices=['remoteclip', 'clip'], help='pre-trained model')
    parser.add_argument('--model_type', type=str, default='ViT-L-14', choices=['RN50', 'ViT-B-32', 'ViT-L-14'], help='pre-trained model type')
    parser.add_argument('--dataset', type=str, default='patternnet', choices=['dlrsd', 'patternnet', 'seasons'], help='choose dataset')
    parser.add_argument('--dataset_path', type=str, default='/mnt/datalv/bill/datasets/data/PatternNet/', help='PatternNet dataset path')
    parser.add_argument('--size', type=int, default=224, help='resize and crop size')
    parser.add_argument('--batch_size', type=int, default=128, help='dataloader batch size')
    args = parser.parse_args()

    # Load model and tokenizer
    model, preprocess_images, tokenizer = load_model(MODEL_NAME, args.model_type)

    # Load dataset, extract and save features
    if args.dataset == 'patternnet':
        full_dataset_path = os.path.join(DATASET_PATH, 'patternnet.csv')
        full_dataset = PatternNet(full_dataset_path, image_transforms=preprocess_images, root=DATASET_PATH)
        full_dataloader = DataLoader(full_dataset, batch_size=args.batch_size, shuffle=False, num_workers=8, pin_memory=True, drop_last=False)
        
        save_path = os.path.join(DATASET_PATH, 'features', f'patternnet_{MODEL_NAME}_tuples.pkl')
        save_dataset(model, full_dataloader, save_path)