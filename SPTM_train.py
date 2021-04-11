import argparse
import torch
from torchvision import transforms, datasets
from torch.utils.data import Dataset, DataLoader
import torch.nn.functional as F
import cv2
import numpy as np
import os
import glob
import shutil
import time
from torchvision.models import resnet18
from PIL import Image
from sklearn.metrics import roc_auc_score
from skimage import io
#from torch import divide as tor_divide
import matplotlib.pyplot as plt 
import pathlib 

#imagenet
mean_train = [0.485, 0.456, 0.406]
std_train = [0.229, 0.224, 0.225]

# def calc_avg_mean_std(img_names, img_root):
#     mean_sum = np.array([0., 0., 0.])
#     std_sum = np.array([0., 0., 0.])
#     n_images = len(img_names)
#     for img_name in img_names:
#         img = cv2.imread(os.path.join(img_root, img_name))
#         img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
#         mean, std = cv2.meanStdDev(img)
#         mean_sum += np.squeeze(mean)
#         std_sum += np.squeeze(std)
#     return (mean_sum / n_images / 255, std_sum / n_images / 255)

def data_transforms(input_size=256, mean_train=mean_train, std_train=std_train):
    data_transforms = transforms.Compose([
            #transforms.ToPILImage(),# PIL型へ変更する。
            transforms.Resize((input_size, input_size)),# 順番が違ったみたい。→Resize→tensorで動く。
            transforms.ToTensor(),
            transforms.Normalize(mean=mean_train,
                                std=std_train)])
    return data_transforms

# def data_transforms_inv():
#     data_transforms_inv = transforms.Compose([transforms.Normalize(mean=list(-np.divide(mean_train, std_train)), std=list(np.divide(1, std_train)))])
#     return data_transforms_inv

def copy_files(src, dst, ignores=[]):
    src_files = os.listdir(src)
    for file_name in src_files:
        ignore_check = [True for i in ignores if i in file_name]
        if ignore_check:
            continue
        full_file_name = os.path.join(src, file_name)
        if os.path.isfile(full_file_name):
            shutil.copy(full_file_name, os.path.join(dst,file_name))
        if os.path.isdir(full_file_name):
            os.makedirs(os.path.join(dst, file_name), exist_ok=True)
            copy_files(full_file_name, os.path.join(dst, file_name), ignores)


def cal_loss(fs_list, ft_list, criterion):
    tot_loss = 0
    for i in range(len(ft_list)):
        fs = fs_list[i]
        ft = ft_list[i]
        _, _, h, w = fs.shape
        #fs_norm = torch.divide(fs, torch.norm(fs, p=2, dim=1, keepdim=True))
        #ft_norm = torch.divide(ft, torch.norm(ft, p=2, dim=1, keepdim=True))
        fs_norm = torch.div(fs, torch.norm(fs, p=2, dim=1, keepdim=True))
        ft_norm = torch.div(ft, torch.norm(ft, p=2, dim=1, keepdim=True))
        f_loss = (0.5/(w*h))*criterion(fs_norm, ft_norm)
        tot_loss += f_loss
    return tot_loss

def cal_anomaly_map(fs_list, ft_list, out_size=256):
    pdist = torch.nn.PairwiseDistance(p=2, keepdim=True)
    anomaly_map = torch.ones([ft_list[0].shape[0], 1, out_size, out_size]).to(device)
    for i in range(len(ft_list)):
        fs = fs_list[i]
        ft = ft_list[i]
        #fs_norm = torch.divide(fs, torch.norm(fs, p=2, dim=1, keepdim=True))
        #ft_norm = torch.divide(ft, torch.norm(ft, p=2, dim=1, keepdim=True))
        fs_norm = torch.div(fs, torch.norm(fs, p=2, dim=1, keepdim=True))
        ft_norm = torch.div(ft, torch.norm(ft, p=2, dim=1, keepdim=True))
        a_map = 0.5*pdist(fs_norm, ft_norm)**2
        a_map = F.interpolate(a_map, size=out_size, mode='bilinear')
        anomaly_map *= a_map
    return anomaly_map

def plot_save_fig(savepath,original,anomaly_map,gt):
    fig = plt.figure()
    ax1 = fig.add_subplot(131)
    ax1.imshow(original)

    ax2 = fig.add_subplot(132)
    ax2.imshow(anomaly_map,"gray")

    ax3 = fig.add_subplot(133)
    ax3.imshow(gt,"gray")

    plt.savefig(savepath)
    plt.close("all")

def get_args():
    parser = argparse.ArgumentParser(description='ANOMALYDETECTION')
    parser.add_argument('--dataset_path', default=r'D:\異常検知\AutoEncoder_vs_MetricLearning\data\carpet')
    parser.add_argument('--num_epoch', default=100)
    parser.add_argument('--lr', default=0.4)
    parser.add_argument('--batch_size', default=32)
    parser.add_argument('--input_size', default=256)
    parser.add_argument('--project_path', default=r'D:\異常検知\STPM_anomaly_detection\carpet_2')
    parser.add_argument('--save_weight', default=False)
    parser.add_argument('--save_src_code', default=False)
    args = parser.parse_args()
    return args

if __name__ == '__main__':
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print ('Available devices ', torch.cuda.device_count())
    print ('Current cuda device ', torch.cuda.current_device())
    print(torch.cuda.get_device_name(device))

    ################################################
    ###             Set Parameters               ###
    ################################################
    
    args = get_args()
    dataset_path = args.dataset_path
    num_epochs = args.num_epoch
    lr = args.lr
    batch_size = args.batch_size
    save_weight = args.save_weight
    input_size = args.input_size
    save_src_code = args.save_src_code
    project_path = args.project_path
    os.makedirs(project_path,exist_ok=True)
    os.makedirs(os.path.join(project_path,"imgs"),exist_ok=True)
    if save_weight:
        weight_save_path = os.path.join(project_path, 'saved')
        os.makedirs(weight_save_path, exist_ok=True)
    if save_src_code:
        source_code_save_path = os.path.join(project_path, 'src')
        os.makedirs(source_code_save_path, exist_ok=True)
        copy_files('./', source_code_save_path, ['.git','.vscode','__pycache__','logs','README']) # copy source code

    ################################################
    ###             Define Dataset               ###
    ################################################
    # calc mean, std
    # train_root_path = os.path.join(dataset_path, 'train', 'good')
    # mean_train, std_train = calc_avg_mean_std(os.listdir(train_root_path), train_root_path)
    # print("mean_train : ", mean_train)
    # print("mean_train : ", std_train)

    data_transform = data_transforms(input_size=input_size, mean_train=mean_train, std_train=std_train)
    # data_transforms_inv = data_transforms_inv()
    image_datasets = datasets.ImageFolder(root=os.path.join(dataset_path, 'train'), transform=data_transform)
    dataloaders = DataLoader(image_datasets, batch_size=batch_size, shuffle=True, num_workers=0, pin_memory=True)
    dataset_sizes = {'train': len(image_datasets)}

    ################################################
    ###             Define Network               ###
    ################################################
    features_t = []
    features_s = []
    def hook_t(module, input, output):
        features_t.append(output)
    def hook_s(module, input, output):
        features_s.append(output)

    model_t = resnet18(pretrained=True).to(device)
    model_t.layer1[-1].register_forward_hook(hook_t)
    model_t.layer2[-1].register_forward_hook(hook_t)
    model_t.layer3[-1].register_forward_hook(hook_t)

    model_s = resnet18(pretrained=False).to(device)
    model_s.layer1[-1].register_forward_hook(hook_s)
    model_s.layer2[-1].register_forward_hook(hook_s)
    model_s.layer3[-1].register_forward_hook(hook_s)

    criterion = torch.nn.MSELoss(reduction='sum')
    optimizer = torch.optim.SGD(model_s.parameters(), lr=lr, momentum=0.9, weight_decay=0.0001)

    ################################################
    ###               Start Train                ###
    ################################################

    start_time = time.time()
    global_step = 0
    print('Dataset size : Train set - {}'.format(dataset_sizes['train']))
    for epoch in range(num_epochs):
        print('-'*20)
        print('Time consumed : {}s'.format(time.time()-start_time))
        print('Epoch {}/{}'.format(epoch, num_epochs - 1))
        print('-'*20)
        model_t.eval()
        model_s.train()
        for idx, (batch, labels) in enumerate(dataloaders): # batch loop
            global_step += 1
            batch = batch.to(device)
            optimizer.zero_grad()
            with torch.set_grad_enabled(True):
                
                _ = model_t(batch)
                _ = model_s(batch)
                # get loss using features.
                loss = cal_loss(features_s, features_t, criterion)
                loss.backward()
                optimizer.step()

                features_t = []
                features_s = []

            if idx%2 == 0:
                print('Epoch : {} | Loss : {:.4f}'.format(epoch, float(loss.data)))

    print('Total time consumed : {}'.format(time.time() - start_time))
    print('Train end.')

    ################################################
    ###               Start Test                 ###
    ################################################

    print('Test phase start')
    model_s.eval() # check
    model_t.eval()
    # anomaly_maps = []
    # ground_truths = []
    test_path = os.path.join(dataset_path, 'test')
    gt_path = os.path.join(dataset_path, 'ground_truth')
    test_imgs = glob.glob(test_path + '/[!good]*/*.png', recursive=True)
    gt_imgs = glob.glob(gt_path + '/[!good]*/*.png', recursive=True)
    test_good_imgs = glob.glob(test_path + '/[good]*/*.png', recursive=True)
    
    gt_val_list = []
    anomaly_val_list = []
    auc_score_list = []
    start_time = time.time()
    for i in range(len(test_imgs)):
        test_img_path = test_imgs[i]
        gt_img_path = gt_imgs[i]
        assert os.path.split(test_img_path)[1].split('.')[0] == os.path.split(gt_img_path)[1].split('_')[0], "Something wrong with test and ground truth pair!"
        #test_img_o = cv2.imread(test_img_path)
        test_img_o = io.imread(test_img_path)
        test_img_resize = cv2.resize(test_img_o, (input_size, input_size))# 保存用
        test_img = Image.fromarray(test_img_o)
        test_img = data_transform(test_img)
        test_img = torch.unsqueeze(test_img, 0).to(device)
        with torch.set_grad_enabled(False):
            _ = model_t(test_img)
            _ = model_s(test_img)
        anomaly_map = cal_anomaly_map(features_s, features_t, out_size=input_size)
        anomaly_map = anomaly_map[0,0,:,:].to('cpu').detach().numpy().ravel()
        #gt_img = cv2.imread(gt_img_path,0)
        gt_img = io.imread(gt_img_path,0)
        gt_img = cv2.resize(gt_img, (input_size, input_size)).ravel()//255
        gt_val_list.extend(gt_img)
        anomaly_val_list.extend(anomaly_map)
        features_t = []
        features_s = []

        name = pathlib.Path(test_img_path).name
        folder = pathlib.Path(test_img_path).parent.name

        
        plot_save_fig(os.path.join(project_path,"imgs",folder+"_"+name),test_img_resize,
                        anomaly_map.reshape((256,256)),gt_img.reshape((256,256)))
    
    # 良品画像
    good_features = []
    for test_img_path in test_good_imgs:
        test_img_o = io.imread(test_img_path)
        test_img_resize = cv2.resize(test_img_o, (input_size, input_size))# 保存用
        test_img = Image.fromarray(test_img_o)
        test_img = data_transform(test_img)
        test_img = torch.unsqueeze(test_img, 0).to(device)
        with torch.set_grad_enabled(False):
            _ = model_t(test_img)
            _ = model_s(test_img)
        anomaly_map = cal_anomaly_map(features_s, features_t, out_size=input_size)
        anomaly_map = anomaly_map[0,0,:,:].to('cpu').detach().numpy().ravel()
        features_t = []
        features_s = []

        good_features.extend(anomaly_map)

        name = pathlib.Path(test_img_path).name
        folder = pathlib.Path(test_img_path).parent.name

        plot_save_fig(os.path.join(project_path,"imgs",folder+"_"+name),test_img_resize,
                        anomaly_map.reshape((256,256)),np.zeros((256,256)))

    print('Total test time consumed : {}'.format(time.time() - start_time))
    print("Total auc score is :")
    print(roc_auc_score(gt_val_list, anomaly_val_list))
    # save data 
    save_anomaly_val_array = np.array(anomaly_val_list)
    save_gt_val_array = np.array(gt_val_list)
    save_good_features = np.array(good_features)

    np.save(os.path.join(project_path,"carpet_anomaly_val"),save_anomaly_val_array)
    np.save(os.path.join(project_path,"carpet_gt_val"),save_gt_val_array)
    np.save(os.path.join(project_path,"carpet_good_val"),save_good_features)





