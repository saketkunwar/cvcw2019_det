from __future__ import division

from models import *
from utils.utils import *
from utils.datasets import *

import os
import sys
import time
import datetime
import argparse
import json

from PIL import Image

import torch
from torch.utils.data import DataLoader
from torchvision import datasets
from torch.autograd import Variable

import matplotlib.pyplot as plt
import matplotlib.patches as patches
from matplotlib.ticker import NullLocator
from thop import profile
    
if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--image_folder", type=str, default="data/tigersamples", help="path to dataset")
    parser.add_argument("--model_def", type=str, default="config/tinytiger.cfg", help="path to model definition file")
    parser.add_argument("--weights_path", type=str, default="checkpoints/km_adam_yolov3_tinytiger_ckpt_9.pth", help="path to weights file")
    parser.add_argument("--class_path", type=str, default="data/tiger/classes.names", help="path to class label file")
    parser.add_argument("--conf_thres", type=float, default=0.5, help="object confidence threshold")
    parser.add_argument("--nms_thres", type=float, default=0.4, help="iou thresshold for non-maximum suppression")
    parser.add_argument("--batch_size", type=int, default=1, help="size of the batches")
    parser.add_argument("--n_cpu", type=int, default=0, help="number of cpu threads to use during batch generation")
    parser.add_argument("--img_size", type=int, default=416, help="size of each image dimension")
    parser.add_argument("--checkpoint_model", type=str, help="path to checkpoint model")
    parser.add_argument("--result_file" ,type=str , required=True)
    opt = parser.parse_args()
    print(opt)
    result_file = opt.result_file
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    # Set up model
    model = Darknet(opt.model_def, img_size=opt.img_size).to(device)

    if opt.weights_path.endswith(".weights"):
        # Load darknet weights
        model.load_darknet_weights(opt.weights_path)
    else:
        # Load checkpoint weights
        model.load_state_dict(torch.load(opt.weights_path))
    model.eval()  # Set in evaluation mode

    dataloader = DataLoader(
        ImageFolder(opt.image_folder, img_size=opt.img_size),
        batch_size=opt.batch_size,
        shuffle=False,
        num_workers=opt.n_cpu,
    )

    classes = load_classes(opt.class_path)  # Extracts class labels from file

    Tensor = torch.cuda.FloatTensor if torch.cuda.is_available() else torch.FloatTensor

    imgs = []  # Stores image paths
    img_detections = []  # Stores detections for each image index

    print("\nPerforming object detection num_item =", len(dataloader))
    #prev_time = time.time()
    itime=[]
    for batch_i, (img_paths, input_imgs) in enumerate(dataloader):
        # Configure input
        input_imgs = Variable(input_imgs.type(Tensor))
        # Get detections
        prev_time = time.time()
        with torch.no_grad():
            detections = model(input_imgs)
            detections = non_max_suppression(detections, opt.conf_thres, opt.nms_thres)

        # Log progress
        current_time = time.time()
        inference_time = current_time - prev_time
        itime.append(inference_time)
        prev_time = current_time
        #flops, params = profile(model, inputs=(input_imgs, ))
        print("\t+ Batch %d, Inference Time: %.4f" % (batch_i, inference_time))

        # Save image and detections
        imgs.extend(img_paths)
        img_detections.extend(detections)
    print ('Mean inference time',np.mean(itime))
    # Bounding-box colors
    cmap = plt.get_cmap("tab20b")
    colors = [cmap(i) for i in np.linspace(0, 1, 20)]

    print("creating submission images:")
    # Iterate through images and save plot of detections
    results=[]
    for img_i, (path, detections) in enumerate(zip(imgs, img_detections)):
        print("(%d) Image: '%s'" % (img_i, path))
        # Create plot
        img = np.array(Image.open(path))
        if detections is not None:
            # Rescale boxes to original image
            detections = rescale_boxes(detections, opt.img_size, img.shape[:2])
            unique_labels = detections[:, -1].cpu().unique()
            n_cls_preds = len(unique_labels)
            bbox_colors = random.sample(colors, n_cls_preds)
            for x1, y1, x2, y2, conf, cls_conf, cls_pred in detections:
                box_w = x2 - x1
                box_h = y2 - y1
                anns = {
                        'image_id': path.split('/')[-1].replace('.jpg',''),
                        'category_id': 1,
                        'segmentation': [],
                        'area': (box_w*box_h).item(),
                        'bbox': [x1.item(), y1.item(),box_w.item(),box_h.item()],
                        'score': cls_conf.item(),
                        'iscrowd': 0
                    }
                results.append(anns)
    print ('conf thres',    opt.conf_thres)       
    json.dump(results, open(result_file,'w'))
