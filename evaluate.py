import os
import time
import pickle
import numpy as np
import torch
import open_clip
import argparse
from PIL import Image
import re
from collections import defaultdict
from utils import *


def read_segmaps_dataset_features(pickle_dir):
    with open(pickle_dir, 'rb') as f:
        data = pickle.load(f)
    all_image_features = torch.from_numpy(data['feats'].astype("float32")).float().to('cuda')
    all_maps = data['maps']
    all_label_counts = data['label_counts']
    all_additional_classes = data['additional_classes']
    all_paths = data['paths']
    return all_image_features, all_maps, all_label_counts, all_additional_classes, all_paths

def read_dataset_features(pickle_dir):
    with open(pickle_dir, 'rb') as f:
        data = pickle.load(f)
    all_image_features = torch.from_numpy(data['feats'].astype("float32")).float().to('cuda')
    all_labels = data['labels']
    all_paths = data['paths']
    return all_image_features, all_labels, all_paths

def read_csv(file_path):
    image_filenames = []
    attributes = []
    attribute_values = []
    with open(file_path, newline='') as csvfile:
        csvreader = csv.reader(csvfile)
        for row in csvreader:
            image_filenames.append(row[0])
            attributes.append(row[1])
            attribute_values.append(row[2])
    return image_filenames, attributes, attribute_values

def find_relative_indices(query_paths, paths):
    path_index_map = {os.path.basename(path): i for i, path in enumerate(paths)}
    relative_indices = []
    for query_path in query_paths:
        index = path_index_map.get(query_path)
        if index is not None:
            relative_indices.append(index)
    return relative_indices

def create_prompts(paired):
    # Store attributes for each category
    category_to_attributes = defaultdict(set)
    for category, attribute in paired:
        category_to_attributes[category].add(attribute)
    prompts = []
    for category, attribute in paired:
        # Get all other attributes for this category
        other_attributes = category_to_attributes[category] - {attribute}
        # Add each other attribute to the new list
        # If there are multiple other attributes, add them all
        other_attributes = list(other_attributes)
        prompts.append(other_attributes)
    return prompts

def metrics_calc2(rankings, prompt, paths, filename_to_index_map, attribute_values, at):
    metrics = {}
    # Convert rankings to filenames to find their corresponding attribute values
    retrieved_filenames = [os.path.basename(paths[idx]) for idx in rankings]

    # Find indices in query_filenames using the precomputed map
    retrieved_indices = [filename_to_index_map.get(filename, -1) for filename in retrieved_filenames]

    # Determine if each retrieval is relevant (True or False)
    is_relevant = [attribute_values[idx] == prompt if idx != -1 else False for idx in retrieved_indices]

    # Calculate Average Precision (AP)
    precisions = []
    relevant_count = 0
    for k, rel in enumerate(is_relevant, start=1):
        if rel:
            relevant_count += 1
            precisions.append(relevant_count / k)

    ap = sum(precisions) / len(precisions) if precisions else 0
    metrics["AP"] = round(ap * 100, 2)

    # Calculate Precision@k and Recall@k
    total_relevant = sum(is_relevant)
    for k in at:
        relevant_at_k = sum(is_relevant[:k])
        precision_at_k = relevant_at_k / k if k else 0
        recall_at_k = relevant_at_k / total_relevant if total_relevant else 0

        metrics[f"P@{k}"] = round(precision_at_k * 100, 2)
        metrics[f"R@{k}"] = round(recall_at_k * 100, 2)

    return metrics


def metrics_calc(rankings, cls, label_counts, classes_change, query_index, at):
    metrics = {}
    query_classes = set(key for key, val in label_counts[query_index].items() if val > 0)
    cls_id = list(classes_change.keys())[list(classes_change.values()).index(cls)]
    query_classes.add(cls_id)  # Add the additional class

    relevant_ranking_indices = [idx for idx in range(len(rankings)) if query_classes.issubset(set(key for key, val in label_counts[rankings[idx]].items() if val > 0))]
    
    precisions = []
    for idx, rank in enumerate(relevant_ranking_indices, start=1):
        precision_at_rank = idx / (rank + 1)  # rank is zero-indexed
        precisions.append(precision_at_rank)

    ap = sum(precisions) / len(precisions) if precisions else 0
    metrics["AP"] = round(ap*100, 2)

    for k in at:
        top_k_indices = rankings[:k]

        # Count how many retrieved items are relevant
        relevant_count = sum(idx in relevant_ranking_indices for idx in top_k_indices)

        # Calculate Recall@k and Precision@k
        recall_at_k = relevant_count / len(query_classes) if query_classes else 0
        precision_at_k = relevant_count / k if k else 0

        metrics[f"R@{k}"] = round(recall_at_k*100, 2)
        metrics[f"P@{k}"] = round(precision_at_k*100, 2)

    return metrics

def calculate_rankings(method, query_features, text_features, database_features, lam=0.5):

    if np.array([x in method for x in ['Image', 'Average Similarities', 'Weighted Similarities', 'Add Similarities', 'Multiply Similarities', 'Minimum Similarity']]).any():
        sim_img = (query_features @ database_features.t())
    if np.array([x in method for x in ['Text', 'Average Similarities', 'Weighted Similarities', 'Add Similarities', 'Multiply Similarities', 'Minimum Similarity']]).any():    
        sim_text = (text_features @ database_features.t())

    if "norm" in method.lower():
        sim_img = norm_cdf(sim_img)
        sim_text = norm_cdf(sim_text)

    if "image only" in method.lower():
        ranks = torch.argsort(sim_img, descending=True)
    elif "text only" in method.lower():
        ranks = torch.argsort(sim_text, descending=True)
    elif "average similarities" in method.lower():
        ranks = torch.argsort((sim_img + sim_text)/2, descending=True)
    elif "weighted similarities" in method.lower():
         ranks = torch.argsort((1-lam)*sim_img + lam*sim_text, descending=True)
    elif "add similarities" in method.lower():
        ranks = torch.argsort(sim_img + sim_text, descending=True)
    elif "multiply similarities" in method.lower():
        ranks = torch.argsort(torch.mul(sim_img, sim_text), descending=True)
    elif "minimum similarity" in method.lower():
        ranks = torch.argsort(torch.maximum(sim_img, sim_text), descending=False)
    
    return ranks.detach().cpu()

if __name__=="__main__":
    parser = argparse.ArgumentParser(description='Evaluating extracted features for Remote Sensing Composed Image Retrieval.')
    parser.add_argument('--model_name', type=str, default='remoteclip', choices=['remoteclip', 'clip'], help='pre-trained model')
    parser.add_argument('--model_type', type=str, default='ViT-L-14', choices=['RN50', 'ViT-B-32', 'ViT-L-14'], help='pre-trained model type')
    parser.add_argument('--dataset', type=str, default='patternnet', choices=['dlrsd', 'patternnet', 'seasons'], help='choose dataset')
    parser.add_argument('--attributes', nargs='+', default=['color'], choices=['color', 'shape', 'density', 'quantity', 'context', 'existence'], help='a list of attributes')
    parser.add_argument('--dataset_path', type=str, default='/mnt/datalv/bill/datasets/data/PatternNet/', help='PatternNet dataset path')
    parser.add_argument('--methods', nargs='+', default=["Weighted Similarities Norm"], choices=["Image only", "Text only", "Average Similarities", "Weighted Similarities Norm"], help='methods to evaluate')
    args = parser.parse_args()

    # Load model and tokenizer
    model, _, tokenizer = load_model(args.model_name, args.model_type)

    # Read features
    if args.dataset == 'patternnet':
        print('Reading features...')
        features, labels, paths = read_dataset_features(os.path.join(args.dataset_path, 'features', f'patternnet_{args.model_name}.pkl'))
        print('Features are loaded!')
        at = [5, 10, 15, 20]

    # Create metrics dict
    metrics_final = create_metrics_final(at, args.methods)
    if args.dataset == 'patternnet':
        #lams = [x*0.1 for x in range(10)]
        lams = [0.5]
        for lam in lams:
            for attribute in args.attributes:
                metrics_final = create_metrics_final(at, args.methods)
                start = time.time()
                query_filenames, attributes, attribute_values = read_csv(f'patterncom/v2/dataset_{attribute}.csv')
                query_labels = [re.split(r'\d', path)[0] for path in query_filenames] # or something like labels[relative_indices], should give the same
                
                # This part is in order to find the prompts
                # Merge attribute with class strings for convenience
                query_attributelabels = [x + query_labels[ii] for ii, x in enumerate(attributes)]
                # We need to manually replace these, cause they are rising issues
                if attribute == 'density':
                    query_attributelabels = [x.replace('densitydenseresidential', 'densityresidential') for x in query_attributelabels]
                    query_attributelabels = [x.replace('densitysparseresidential', 'densityresidential') for x in query_attributelabels]
                    query_attributelabels = [x.replace('densitychristmastreefarm', 'densitytreecover') for x in query_attributelabels]
                    query_attributelabels = [x.replace('densityforest', 'densitytreecover') for x in query_attributelabels]
                elif attribute == 'shape':
                    query_attributelabels = [x.replace('shapeclosedroad', 'shaperoad') for x in query_attributelabels]
                    query_attributelabels = [x.replace('shapeintersection', 'shaperoad') for x in query_attributelabels]
                elif attribute == 'context':
                    query_attributelabels = [x.replace('contextbridge', 'contextroadpass') for x in query_attributelabels]
                    query_attributelabels = [x.replace('contextoverpass', 'contextroadpass') for x in query_attributelabels]
                elif attribute == 'existence':
                    query_attributelabels = [x.replace('existenceferryterminal', 'existencepier') for x in query_attributelabels]
                    query_attributelabels = [x.replace('existenceharbor', 'existencepier') for x in query_attributelabels]
                    query_attributelabels = [x.replace('existenceparkingspace', 'existenceparking') for x in query_attributelabels]
                    query_attributelabels = [x.replace('existenceparkinglot', 'existenceparking') for x in query_attributelabels]
                paired = list(zip(query_attributelabels, attribute_values))
                # Create a prompt list with all possible attributes (per class) except the one associated with the current item
                # This will allow each query to retrieve images with all other attributes except its own.
                prompts = create_prompts(paired)
                relative_indices = find_relative_indices(query_filenames, paths)
                filename_to_index_map = {filename: i for i, filename in enumerate(query_filenames)}
                
                text_feature_cache = {}
                for i, idx in enumerate(relative_indices):
                    print(f'Retrieval running for query {i}', end='\r')
                    query_feature = features[idx]
                    for prompt in prompts[i]:
                        # Check if the text feature for this prompt is already computed
                        if prompt not in text_feature_cache:
                            # If not, compute and cache it
                            text = tokenizer(prompt).to('cuda')
                            text_feature = model.encode_text(text)
                            text_feature = (text_feature / text_feature.norm(dim=-1, keepdim=True)).squeeze().detach().to(torch.float32)
                            text_feature_cache[prompt] = text_feature
                        else:
                            # If already computed, retrieve from cache
                            text_feature = text_feature_cache[prompt]
                        for method in args.methods:
                            rankings = calculate_rankings(method, query_feature, text_feature, features, lam)
                            temp_metrics = metrics_calc2(rankings, prompt, paths, filename_to_index_map, attribute_values, at)

                            # Accumulate metrics for each method
                            for k in at:
                                metrics_final[method][f"R@{k}"].append(temp_metrics[f"R@{k}"])
                                metrics_final[method][f"P@{k}"].append(temp_metrics[f"P@{k}"])
                            metrics_final[method]["AP"].append(temp_metrics["AP"])

                # Calculate the average for each metric
                for method in metrics_final:
                    for metric in metrics_final[method]:
                        metrics_final[method][metric] = round(sum(metrics_final[method][metric]) / len(metrics_final[method][metric]) if metrics_final[method][metric] else 0, 2)

                print(metrics_final)
                end = time.time()
                timer(start, end)

                print('Writing results to CSV file...')
                dict_to_csv(metrics_final, os.path.join('results', args.dataset + f'_metrics_{str(args.model)}_{attribute}_{str(lam)}.csv')) #time.strftime("%Y_%m_%d_%H_%M_%S")+'.csv')