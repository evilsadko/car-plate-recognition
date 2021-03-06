import numpy as np
import functools
import glob
import itertools
import multiprocessing
import random
import sys
import time

import cv2
import numpy
import tensorflow as tf
import common
import gen_all_2 as gen

import tensorflow as tf
import common
import keras
from keras import layers
from keras.layers import (
    Conv2D, MaxPooling2D,
    Input, Dense, Activation,
    Reshape, Lambda,
    BatchNormalization
)

WINDOW_SHAPE = (64, 128)

def imgs(x):
      cv2.imshow('Rotat', numpy.array(x))
      cv2.waitKey(0)
      cv2.destroyAllWindows()

def code_to_vec(p, code):
    def char_to_vec(c):
        y = numpy.zeros((len(common.CHARS),))
        #print c
        y[common.CHARS.index(c)] = 1.0
        return y

    c = numpy.vstack([char_to_vec(c) for c in code])
    
    return numpy.concatenate([[1. if p else 0], c.flatten()])

#00000008_QE8657PB_1.png
def read_data(img_glob):
    for fname in sorted(glob.glob(img_glob)):
        im = cv2.imread(fname)[:, :, 0].astype(numpy.float32) / 255.
        code = fname.split("_")[1]
        if len(code) < 9:
           poix = 9 - len(code)
           
           for ox in range(poix):
               code += " "
        p = fname.split("_")[-1].split(".")[0] == '1'
        #print len(code), code
        yield im, code_to_vec(p, code)


def unzip(b):
    xs, ys = zip(*b)
    xs = numpy.array(xs)
    ys = numpy.array(ys)
    return xs, ys


def batch(it, batch_size):
    out = []
    for x in it:
        out.append(x)
        if len(out) == batch_size:
            yield out
            out = []
    if out:
        yield out


def mpgen(f):
    def main(q, args, kwargs):
        try:
            for item in f(*args, **kwargs):
                q.put(item)
        finally:
            q.close()

    @functools.wraps(f)
    def wrapped(*args, **kwargs):
        q = multiprocessing.Queue(3) 
        proc = multiprocessing.Process(target=main,
                                       args=(q, args, kwargs))
        proc.start()
        try:
            while True:
                item = q.get()
                yield item
        finally:
            proc.terminate()
            proc.join()

    return wrapped
        

@mpgen
def read_batches(batch_size):
    g = gen.generate_ims()
    #print (">>>>>>>>>>>>>>>")
    def gen_vecs():
        for im, c, p in itertools.islice(g, batch_size):
            if len(c) < 9:
                poix = 9 - len(c)
                for ox in range(poix):
                    c += " "
            #print len(c)
            yield im.astype(numpy.float32) / 255., code_to_vec(p, c)

    while True:
        yield unzip(gen_vecs())


def get_loss(y, y_):
    # Calculate the loss from digits being incorrect.  Don't count loss from
    # digits that are in non-present plates.
    digits_loss = tf.nn.softmax_cross_entropy_with_logits(
                                          logits=tf.reshape(y[:, 1:],
                                                     [-1, len(common.CHARS)]),
                                          labels=tf.reshape(y_[:, 1:],
                                                     [-1, len(common.CHARS)]))
    digits_loss = tf.reshape(digits_loss, [-1, 9])
    digits_loss = tf.reduce_sum(digits_loss, 1)
    digits_loss *= (y_[:, 0] != 0)
    digits_loss = tf.reduce_sum(digits_loss)

    # Calculate the loss from presence indicator being wrong.
    presence_loss = tf.nn.sigmoid_cross_entropy_with_logits(
                                                          logits=y[:, :1], labels=y_[:, :1])
    presence_loss = 9 * tf.reduce_sum(presence_loss)

    return digits_loss, presence_loss, digits_loss + presence_loss
# Utility functions
def weight_variable(shape):
  initial = tf.truncated_normal(shape, stddev=0.1)
  return tf.Variable(initial)


def bias_variable(shape):
  initial = tf.constant(0.1, shape=shape)
  return tf.Variable(initial)


def conv2d(x, W, stride=(1, 1), padding='SAME'):
  return tf.nn.conv2d(x, W, strides=[1, stride[0], stride[1], 1],
                      padding=padding)


def max_pool(x, ksize=(2, 2), stride=(2, 2)):
  return tf.nn.max_pool(x, ksize=[1, ksize[0], ksize[1], 1],
                        strides=[1, stride[0], stride[1], 1], padding='SAME')


def avg_pool(x, ksize=(2, 2), stride=(2, 2)):
  return tf.nn.avg_pool(x, ksize=[1, ksize[0], ksize[1], 1],
                        strides=[1, stride[0], stride[1], 1], padding='SAME')

def res_net_block(input_data, filter_count):
  x = layers.Conv2D(filter_count, (1, 1), activation='relu', padding='same')(input_data)
  x = layers.BatchNormalization()(x)
  x = layers.Conv2D(filter_count, (3, 3), activation=None, padding='same')(x)
  x = layers.BatchNormalization()(x)
  x = tf.nn.relu(x)
  x = layers.Conv2D(filter_count, (1, 1), activation=None, padding='same')(x)
  x = layers.BatchNormalization()(x)
  x = layers.Add()([x, input_data])
  x = tf.nn.relu(x)#x = layers.Activation('relu')(x)
  print (x.shape)
  return x


def convolutional_layers():
    """
    Get the convolutional layers of the model.
    """
    x_ = tf.placeholder(tf.float32, [None, 64, 128])
    x_expanded = tf.expand_dims(x_, 3)
    print ("IN", x_expanded.shape)
    # First layer
    x = Conv2D(32, (3, 3), padding='same', name='conv1', kernel_initializer='he_normal')(x_expanded)
    x = BatchNormalization()(x)
    x = Activation('relu')(x)
    x = MaxPooling2D(pool_size=(2, 2), name='max1')(x)
    print (x.shape)
    x = Conv2D(64, (3, 3), padding='same', name='conv2', kernel_initializer='he_normal')(x)
    x = BatchNormalization()(x)
    x = Activation('relu')(x)
    x = MaxPooling2D(pool_size=(2, 2), name='max2')(x)
    print (x.shape)
    x = res_net_block(x, 64)
    print (x.shape)
    x = Conv2D(128, (3, 3), padding='same', name='conv3', kernel_initializer='he_normal')(x)
    x = BatchNormalization()(x)
    x = Activation('relu')(x)
    x = MaxPooling2D(pool_size=(2, 2), name='max3')(x)
    print (x.shape)
    x = res_net_block(x, 128)    
    print (x.shape)
    x = Conv2D(128, (3, 3), padding='same', name='conv4', kernel_initializer='he_normal')(x)
    x = BatchNormalization()(x)
    x = Activation('relu')(x)
    x = MaxPooling2D(pool_size=(1, 2), name='max4')(x)
    print (x.shape)
    x = Conv2D(128, (3, 3), padding='valid', name='conv5', kernel_initializer='he_normal')(x)

    x = BatchNormalization()(x)
    x = Activation('relu')(x)    
    print (x.shape)
    # Densely connected layer
    W_fc1 = weight_variable([1 * 1 * 128, 2048])
    b_fc1 = bias_variable([2048])
    conv_layer_flat = tf.reshape(x, [-1, 1 * 1 * 128])
    h_fc1 = tf.nn.relu(tf.matmul(conv_layer_flat, W_fc1) + b_fc1)
 
    W_fc2 = weight_variable([2048, 1 + 9 * len(common.CHARS)])
    b_fc2 = bias_variable([1 + 9 * len(common.CHARS)])

    y = tf.matmul(h_fc1, W_fc2) + b_fc2
 
    
    return x_, y
    
#model = convolutional_layers()    

def train(learn_rate, report_steps, batch_size, initial_weights=None):
    x, y = convolutional_layers()
    y_ = tf.placeholder(tf.float32, [None, 9 * len(common.CHARS) + 1])
    #model = keras.Model(x, y)

    digits_loss, presence_loss, loss = get_loss(y, y_)
    train_step = tf.train.AdamOptimizer(learn_rate).minimize(loss)

    best = tf.argmax(tf.reshape(y[:, 1:], [-1, 9, len(common.CHARS)]), 2)
    correct = tf.argmax(tf.reshape(y_[:, 1:], [-1, 9, len(common.CHARS)]), 2)

    init = tf.initialize_all_variables()

    def vec_to_plate(v):
        return "".join(common.CHARS[i] for i in v)

    def do_report():
        r = sess.run([best,
                      correct,
                      tf.greater(y[:, 0], 0),
                      y_[:, 0],
                      digits_loss,
                      presence_loss,
                      loss],
                     feed_dict={x: test_xs, y_: test_ys})
        num_correct = numpy.sum(
                        numpy.logical_or(
                            numpy.all(r[0] == r[1], axis=1),
                            numpy.logical_and(r[2] < 0.5,
                                              r[3] < 0.5)))
        r_short = (r[0][:190], r[1][:190], r[2][:190], r[3][:190])
        for b, c, pb, pc in zip(*r_short):
            print ("{} {} <-> {} {}".format(vec_to_plate(c), pc,
                                           vec_to_plate(b), float(pb)))
        num_p_correct = numpy.sum(r[2] == r[3])
        "B{:3d} {:2.02f}% {:02.02f}% loss: {} (digits: {}, presence: {}) |{}|"
        print (
            batch_idx,
            100. * num_correct / (len(r[0])),
            100. * num_p_correct / len(r[2]),
            r[6],
            r[4],
            r[5],
            "".join("X "[numpy.array_equal(b, c) or (not pb and not pc)]
                                           for b, c, pb, pc in zip(*r_short)))

    def do_batch():
        sess.run(train_step,
                 feed_dict={x: batch_xs, y_: batch_ys})
        #imgs(batch_xs[0])
        if batch_idx % report_steps == 0:
            do_report()

    saver = tf.train.Saver()
    gpu_options = tf.GPUOptions(per_process_gpu_memory_fraction=0.60)
    with tf.Session(config=tf.ConfigProto(gpu_options=gpu_options)) as sess:
        if initial_weights is not None:
            saver.restore(sess, "model/model.ckpt")
        else:    
            sess.run(init)

        test_xs, test_ys = unzip(list(read_data("test/*.png"))[:50])
        #imgs(test_xs[3])
        #print test_xs[0], test_ys[0].shape
        try:
            last_batch_idx = 0
            last_batch_time = time.time()
            batch_iter = enumerate(read_batches(batch_size))
            for batch_idx, (batch_xs, batch_ys) in batch_iter:
                #print batch_xs[0].shape, batch_ys[0].shape
                #imgs(batch_xs[3])
                do_batch()
                if batch_idx % report_steps == 0:
                    batch_time = time.time()
                    if last_batch_idx != batch_idx:
                        print ("time for 60 batches {}".format(
                            60 * (last_batch_time - batch_time) /
                                            (last_batch_idx - batch_idx)))
                        last_batch_idx = batch_idx
                        last_batch_time = batch_time

        except KeyboardInterrupt:
             #model.save("h.npz")
             save_path = saver.save(sess, "model/model.ckpt")
             print("Model saved in path: %s" % save_path)
             print ("STOP")

def detect():
    x, y = convolutional_layers()
    gpu_options = tf.GPUOptions(per_process_gpu_memory_fraction=0.60)
    saver = tf.train.Saver()
    best = tf.argmax(tf.reshape(y[:, 1:], [-1, 9, len(common.CHARS)]), 2)
    with tf.Session(config=tf.ConfigProto(gpu_options=gpu_options)) as sess:
        saver.restore(sess, "model/model.ckpt")
        #im = cv2.imread("test/00000035_KA1804AO_1.png")[:, :, 0].astype(numpy.float32) / 255.
        im = cv2.imread("/media/sadko/1b32d2c7-3fcf-4c94-ad20-4fb130a7a7d4/PLAYGROUND/OCR/generate_train/test/00000827_B999EX40_1.png")[:, :, 0].astype(numpy.float32) / 255.
        
        im = np.reshape(im,[1,64,128])
        feed_dict = {x: im}
        answ = sess.run(best, feed_dict=feed_dict)
        #letter_probs = (answ[0,0,0,1:].reshape(9, len(common.CHARS)))
        #letter_probs = common.softmax(letter_probs)  
        print (answ.shape, "".join(common.CHARS[i] for i in answ[0]))
        
if __name__ == "__main__":
    if len(sys.argv) > 1:
       initial_weights = sys.argv
    else:
       initial_weights = None

    train(learn_rate=0.001,
          report_steps=20,
          batch_size=50,
          initial_weights=initial_weights)

#    detect()

#    
#model = Sequential()

#x = Input(name='the_input', shape=(228,228,3), dtype='float32')
##tf.placeholder(tf.float32, [50, 64, 128, 3])
#model.add(ResNet50(include_top = False, pooling = "avg", weights=None, input_tensor=x))
#model.add(Dense(1 + 9 * len(common.CHARS), activation = 'softmax'))
##model.layers[0].trainable = False
##1 + 9 * len(common.CHARS)\
#model.summary()
#print (model.output)

#https://stackoverflow.com/questions/33759623/tensorflow-how-to-save-restore-a-model



