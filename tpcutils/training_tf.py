
from tensorflow.keras.callbacks import LearningRateScheduler

class LinearScheduler(LearningRateScheduler):

    def __init__(self, n_epochs, lr_init=0.01):

        def scheduler(epoch, lr):
            if epoch == 0:
                return lr_init
            elif epoch < n_epochs/5:
                return lr*1.1
            else:
                return lr * 0.9

        super().__init__(scheduler)

