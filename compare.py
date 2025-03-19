import torch
from torchvision import models, transforms
from PIL import Image
import torch.nn.functional as F

# 加载预训练的 ResNet 模型
model = models.resnet50(pretrained=True)
model.eval()  

# 特征提取器，提取全局平均池化后的特征
class FeatureExtractor(torch.nn.Module):
    def __init__(self, model):
        super(FeatureExtractor, self).__init__()
        self.features = torch.nn.Sequential(*list(model.children())[:-1])  

    def forward(self, x):
        x = self.features(x)
        x = x.view(x.size(0), -1)  
        return x

feature_extractor = FeatureExtractor(model)

# 图像预处理变换
preprocess = transforms.Compose([
    transforms.Resize(256),
    transforms.CenterCrop(224),
    transforms.ToTensor(),
    transforms.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225]),
])

# 加载图像
def load_image(image_path):
    image = Image.open(image_path).convert('RGB')
    return image

# 提取图像特征
def extract_features(image):
    image = preprocess(image)
    image = image.unsqueeze(0)  # 添加批次维度
    with torch.no_grad():
        features = feature_extractor(image)
    return features

# 计算余弦相似度
def cosine_similarity(features1, features2):
    similarity = F.cosine_similarity(features1, features2)
    return similarity.item()

if __name__ == "__main__":
    image1_path = "D:/hanzi_project/test/欲.jpg"
    image2_path = "D:/hanzi_project/test/别.jpg"

    image1 = load_image(image1_path)
    image2 = load_image(image2_path)

    features1 = extract_features(image1)
    features2 = extract_features(image2)

    similarity = cosine_similarity(features1, features2)

    print(f"图像相似度: {similarity:.4f}")