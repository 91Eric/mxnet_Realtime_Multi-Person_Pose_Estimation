'''
@author: kohill

'''

from tensorboardX import SummaryWriter
from coco_data_iter import getDataLoader
from resnet_v1_101_deeplab_deconv import get_symbol
import mxnet as mx
import logging,os
import numpy as np
BATCH_SIZE = 8
NUM_LINKS = 19
NUM_PARTS =  20

SAVE_PREFIX = "models/resnet-101"
PRETRAINED_PREFIX = "pre/deeplab_cityscapes"
LOGGING_DIR = "logs"
GLOBAL_STEP_PATH=os.path.join(LOGGING_DIR,"global_step.npy")
def load_checkpoint(prefix, epoch):

    save_dict = mx.nd.load('%s-%04d.params' % (prefix, epoch))
    arg_params = {}
    aux_params = {}
    for k, v in save_dict.items():
        tp, name = k.split(':', 1)
        if tp == 'arg':
            arg_params[name] = v
        if tp == 'aux':
            aux_params[name] = v
    return arg_params, aux_params

def train(retrain = True,ndata = 16,gpus = [0,1],start_n_dataset = 0):
    input_shape = (368,368)
    stride = (8,8)
    sym = get_symbol(is_train = True, numberofparts = NUM_PARTS, numberoflinks= NUM_LINKS)
    
    model = mx.mod.Module(symbol=sym, context=[mx.gpu(g) for g in gpus],label_names  = ["heatmaps","pafmaps","loss_mask"])
    model.bind(data_shapes=[('data', (BATCH_SIZE, 3,input_shape[0],input_shape[1]))],
               label_shapes = [("heatmaps",(BATCH_SIZE,NUM_PARTS ,input_shape[0]//stride[0],input_shape[1]//stride[0])),
                               ("pafmaps",(BATCH_SIZE,NUM_LINKS*2 ,input_shape[0]//stride[0],input_shape[1]//stride[0])),
                               ("loss_mask",(BATCH_SIZE,1 ,input_shape[0]//stride[0],input_shape[1]//stride[0])),
                               ]
               )        
    summary_writer = SummaryWriter(LOGGING_DIR)
    if retrain:
        args,auxes = load_checkpoint(PRETRAINED_PREFIX,0)
    else:
        args,auxes = load_checkpoint(SAVE_PREFIX+"final",start_n_dataset)
        
    model.init_params(arg_params=args, aux_params=auxes, allow_missing=retrain,allow_extra = True,initializer=mx.init.Uniform(0.000001))
    model.init_optimizer(optimizer='RMSprop', 
                        optimizer_params=(('learning_rate', 0.0001 ), ))   
    data_iter = getDataLoader(batch_size = BATCH_SIZE)
    global_step =np.load(GLOBAL_STEP_PATH) if not retrain and os.path.exists(GLOBAL_STEP_PATH) else 0
    for n_data_wheel in range(ndata):
        model.save_checkpoint(SAVE_PREFIX + "final", n_data_wheel + start_n_dataset)        
        for nbatch,data_batch in enumerate( data_iter):
            imgs_batch,heatmaps_batch,pafmaps_batch,loss_mask_batch = list(
                map(lambda x: mx.nd.array(x), data_batch))
            model.forward(mx.io.DataBatch(data = [imgs_batch],label = [heatmaps_batch,pafmaps_batch,loss_mask_batch]), is_train=True) 
            prediction=model.get_outputs()
            heatmap_loss = prediction[0].asnumpy()[0]/BATCH_SIZE
            paf_loss = prediction[1].asnumpy()[0] / BATCH_SIZE            
            summary_writer.add_scalar("heatmap_loss", heatmap_loss,global_step = nbatch)
            summary_writer.add_scalar("paf_loss", paf_loss,global_step=nbatch) 
            logging.info("{0} {1} {2} {3} {4}".format(
                n_data_wheel + start_n_dataset,nbatch, heatmap_loss,paf_loss,prediction[2].asnumpy()[0]))
            model.backward()  
            model.update()        
            if nbatch % 100 == 0:
                model.save_checkpoint(SAVE_PREFIX , nbatch )
                global_step += 100
                np.save(GLOBAL_STEP_PATH,global_step)
if __name__ == "__main__":
    logging.basicConfig(level = logging.INFO)
    train(retrain = True, gpus = [0,1],start_n_dataset = 0)