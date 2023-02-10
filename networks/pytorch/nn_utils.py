import sys

import torch
from torch import nn
from torch.nn import functional as F

class FcNet(nn.Module):
    def __init__(self,input_shape,output_shape=7):
        super(FcNet,self).__init__()

        self.fc1 = nn.Linear(input_shape, 200)
        self.fc2 = nn.Linear(200, 100)
        self.fc3 = nn.Linear(100, 50)
        self.fc4 = nn.Linear(50, output_shape)

    def forward(self, x):
        x = F.relu(self.fc1(x))
        x = F.relu(self.fc2(x))
        x = F.relu(self.fc3(x))
        x = self.fc4(x)
        return x


# class DynamicFcNet(nn.Module):
#     def __init__(self,input_shape,output_shape,nLayers=4,nNodes=[200,100,50]):
#         super(DynamicFcNet,self).__init__()
#
#         self.layers = []
#
#         for layer in
#
#     def forward(self,x):
#
#         x = x
#
#         return x


class EncodeLayer(nn.Module):
    """
        Encoding Layers
    """

    def __init__(self,in_channels,out_channels):
        super(EncodeLayer,self).__init__()

        self.conv1 = nn.Conv2d(in_channels,out_channels,2,stride=2)
        self.pool = nn.MaxPool2d(2,2)

    def forward(self,x):
        x = F.relu(self.conv1(x))
        x = self.pool(x)
        return x

class DecodeLayer(nn.Module):
    """
        Decoding Layers
    """

    def __init__(self,in_channels,out_channels):
        super(DecodeLayer,self).__init__()

        self.Tconv1 = nn.ConvTranspose2d(in_channels,out_channels,3,padding=1)

    def forward(self,x,SigmAct=0):
        if SigmAct:
            x = torch.sigmoid(self.Tconv1(x))
        else:
            x = F.relu(self.Tconv1(x))

        return x

class DeepConvAENet(nn.Module):
    def __init__(self,in_channels,out_channels, filters = [8,32]):
        super(DeepConvAENet,self).__init__()

        assert len(filters) >1, 'Network must contain at least 2 layers'

        self.in_channels = in_channels
        self.out_channels = out_channels
        self.filters = filters

        encoding = []
        encoding.append(EncodeLayer(self.in_channels,self.filters[-1]))
        encoding.extend([EncodeLayer(self.filters[i+1],self.filters[i]) for i in reversed(range(len(filters)-1))])

        self.encoder_layers = nn.Sequential(*encoding)

        decoding = []
        decoding.extend([DecodeLayer(self.filters[i],self.filters[i+1]) for i in range(len(filters)-1)])

        self.decoder_layers = nn.Sequential(*decoding)


        self.outc = DecodeLayer(self.filters[-1],self.out_channels)

    def forward(self,x):

        x_enc = self.encoder_layers(x)
        x_dec = self.decoder_layers(x_enc)

        logits = self.outc(x_dec,True)
        return logits


class DeepConvNet(nn.Module):
    def __init__(self,in_channels,out_channels, filters= [8,32]):
        super(DeepConvNet,self).__init__()

        assert len(filters) > 1, "Network must contain a few layers.."

        self.in_channels = in_channels
        self.out_channels = out_channels
        self.filters = filters

        encoding = []
        encoding.append(EncodeLayer(self.in_channels,self.filters[-1]))
        encoding.extend([EncodeLayer(self.filters[i+1],self.filters[i]) for i in reversed(range(len(filters)-1))])

        self.encoder_layers = nn.Sequential(*encoding)

        self.fc = nn.Linear(filters[0], self.out_channels)

    def forward(self, x):
        x_enc = self.encoder_layers(x)

        x = self.fc(x_enc.flatten())


        return x
