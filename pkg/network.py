import os, time
import tensorflow as tf

from .constants import *

class Network:
    """ Holds nodes of a tensorflow network """
    def __init__(self, graph, x, y_, p_dropout, y, accuracy, precision, recall, train, summaries):
        self.graph = graph
        self.x = x
        self.y_ = y_
        self.p_dropout = p_dropout
        self.y = y
        self.accuracy = accuracy
        self.precision = precision
        self.recall = recall
        self.train = train
        self.summaries = tf.merge_summary(summaries)

def createCoarseNetwork(threshold):
    WEIGHTS_INIT = tf.truncated_normal or tf.random_normal or tf.random_uniform
    BIASES_INIT = 1.0
    ACTIVATION_FUNC = tf.nn.sigmoid or tf.nn.tanh or tf.nn.relu
    PREPROCESS_GRAY = False
    PREPROCESS_HSV = False
    PREPROCESS_NORMALIZE = True
    HIDDEN_LAYERS = [30]
    COST_FUNC = "squared_error"
    OPTIMIZER = "adam" or "gradient_descent" or "adadelta" or \
        "adagrad" or "momentum" or "ftrl" or "rmsprop"
    #helper functions
    def createLayer(input, inSize, outSize, layerName, summaries):
        with tf.name_scope(layerName):
            with tf.name_scope("weights"):
                w = tf.Variable(WEIGHTS_INIT([inSize, outSize]))
                addSummaries(w, summaries, layerName + "/weights", "mean_stddev_hist")
            with tf.name_scope("biases"):
                b = tf.Variable(tf.constant(BIASES_INIT, shape=[outSize]))
                addSummaries(b, summaries, layerName + "/biases", "mean_stddev_hist")
            return ACTIVATION_FUNC(tf.matmul(input, w) + b, "out")
    #create nodes
    summaries = []
    graph = tf.Graph()
    with graph.as_default():
        inputChannels = IMG_CHANNELS
        #input nodes
        with tf.name_scope("input"): #group nodes for easier viewing with tensorboard
            x = tf.placeholder(tf.float32, \
                [None, INPUT_HEIGHT, INPUT_WIDTH, inputChannels], name="x_input")
            y_ = tf.placeholder(tf.float32, [None, 2], name="y_input")
            y2 = tf.slice(y_, [0, 0], [-1, 1])
            p_dropout = tf.placeholder(tf.float32, name="p_dropout") #currently unused
        with tf.name_scope("process_input"):
            if PREPROCESS_GRAY:
                x2 = tf.image.rgb_to_grayscale(x)
                inputChannels = 1
                if PREPROCESS_NORMALIZE:
                    x2 = tf.div(x2, tf.constant(255.0))
            elif PREPROCESS_HSV:
                x2 = tf.div(x, tf.constant(255.0)) #normalisation is required
                x2 = tf.image.rgb_to_hsv(x2)
            else:
                if PREPROCESS_NORMALIZE:
                    x2 = tf.div(x, tf.constant(255.0))
                else:
                    x2 = x
            x_flat = tf.reshape(x2, [-1, INPUT_HEIGHT*INPUT_WIDTH*inputChannels])
            addSummaries(x2, summaries, "input", "image")
        #hidden and output layers
        layerSizes = [INPUT_HEIGHT*INPUT_WIDTH*inputChannels] + HIDDEN_LAYERS
        layer = x_flat
        for i in range(1,len(layerSizes)):
            layer = createLayer(
                layer, layerSizes[i-1], layerSizes[i], "hidden_layer" + str(i), summaries
            )
        y = createLayer(
            layer, layerSizes[-1], 1, "output_layer", summaries
        )
        #cost
        with tf.name_scope("cost"):
            if COST_FUNC == "squared_error":
                cost = tf.square(y2 - y)
            else:
                raise Exception("Unrecognised cost function")
            addSummaries(cost, summaries, "cost", "mean")
        #optimizer
        with tf.name_scope("train"):
            if OPTIMIZER == "adam":
                train = tf.train.AdamOptimizer().minimize(cost)
            elif OPTIMIZER == "gradient_descent":
                train = tf.train.GradientDescentOptimizer(0.01)
            elif OPTIMIZER == "adadelta":
                train = tf.train.AdadeltaOptimizer()
            elif OPTIMIZER == "adagrad":
                train = tf.train.AdagradOptimizer(0.01)
            elif OPTIMIZER == "momentum":
                train = tf.train.MomentumOptimizer(0.01)
            elif OPTIMIZER == "ftrl":
                train = tf.train.FtrlOptimizer(0.01)
            elif OPTIMIZER == "rmsprop":
                train = tf.train.RMSPropOptimizer(0.01)
            else:
                raise Exception("Unrecognised optimizer")
        #metrics
        with tf.name_scope("metrics"):
            y_pred = tf.greater(y, tf.constant(threshold))
            y2_pred = tf.greater(y2, tf.constant(0.5))
            correctness = tf.equal(y_pred, y2_pred)
            #accuracy
            accuracy = tf.reduce_mean(tf.cast(correctness, tf.float32))
            addSummaries(accuracy, summaries, "accuracy", "mean")
            #precision and recall
            truePos = tf.reduce_sum(tf.cast(
                tf.logical_and(correctness, tf.equal(y_pred, tf.constant(True))),
                tf.float32
            ))
            predPos = tf.reduce_sum(tf.cast(y_pred, tf.float32))
            actualPos = tf.reduce_sum(tf.cast(y2_pred, tf.float32))
            prec = tf.cond(
                tf.equal(predPos, tf.constant(0.0)),
                lambda: tf.constant(0.0),
                lambda: truePos / predPos
            )
            rec  = tf.cond(
                tf.equal(actualPos, tf.constant(0.0)),
                lambda: tf.constant(0.0),
                lambda: truePos / actualPos
            )
            addSummaries(prec, summaries, "precision", "mean")
            addSummaries(rec, summaries, "recall", "mean")
    #return output nodes and trainer
    return Network(graph, x, y_, p_dropout, y, accuracy, prec, rec, train, summaries)

def createDetailedNetwork():
    #helper functions
    def createWeights(shape):
        with tf.name_scope("weights"):
            return tf.Variable(tf.truncated_normal(shape, stddev=0.1))
    def createBiases(shape):
        with tf.name_scope("biases"):
            return tf.Variable(tf.constant(0.1, shape=shape))
    def createConv(x, w, b):
        with tf.name_scope("conv"):
            xw = tf.nn.conv2d(x, w, strides=[1, 1, 1, 1], padding="SAME")
            return tf.nn.relu(xw + b)
    def createPool(c):
        with tf.name_scope("pool"):
            return tf.nn.max_pool(c, ksize=[1, 2, 2, 1], strides=[1, 2, 2, 1], padding="SAME")
    #create nodes
    summaries = []
    graph = tf.Graph()
    with graph.as_default():
        inputChannels = IMG_CHANNELS
        #input nodes
        with tf.name_scope("input"): #group nodes for easier viewing with tensorboard
            x = tf.placeholder(tf.float32, [None, INPUT_HEIGHT, INPUT_WIDTH, inputChannels], name="x_input")
            y_ = tf.placeholder(tf.float32, [None, 2], name="y_input")
            p_dropout = tf.placeholder(tf.float32, name="p_dropout")
        with tf.name_scope("process_input"):
            rgb2gray = False
            rgb2hsv = False
            normalise = True
            if rgb2gray:
                x2 = tf.image.rgb_to_grayscale(x)
                inputChannels = 1
                if normalise:
                    x2 = tf.div(x2, tf.constant(255.0))
            elif rgb2hsv:
                x2 = tf.div(x, tf.constant(255.0)) #normalisation is required
                x2 = tf.image.rgb_to_hsv(x2)
            else:
                if normalise:
                    x2 = tf.div(x, tf.constant(255.0))
                else:
                    x2 = x
            addSummaries(x2, summaries, "input", "image")
        #first convolutional layer
        with tf.name_scope("conv_layer1"):
            w1 = createWeights([5, 5, 3, 32]) #filter_height, filter_width, in_channels, out_channels
            b1 = createBiases([32])
            c1 = createConv(x2, w1, b1)
            p1 = createPool(c1)
            #addSummaries(w1, summaries, "conv_layer1", "mean_stddev_hist")
            #addSummaries(b1, summaries, "conv_layer1", "mean_stddev_hist")
        #second convolutional layer
        with tf.name_scope("conv_layer2"):
            w2 = createWeights([5, 5, 32, 64])
            b2 = createBiases([64])
            c2 = createConv(p1, w2, b2)
            p2 = createPool(c2)
            #addSummaries(w2, summaries, "conv_layer2", "mean_stddev_hist")
            #addSummaries(b2, summaries, "conv_layer2", "mean_stddev_hist")
        #densely connected layer
        with tf.name_scope("dense_layer"):
            w3 = createWeights([INPUT_HEIGHT//4 * INPUT_WIDTH//4 * 64, 1024])
            b3 = createBiases([1024])
            p2_flat = tf.reshape(p2, [-1, INPUT_HEIGHT//4 * INPUT_WIDTH//4 * 64])
            h1 = tf.nn.relu(tf.matmul(p2_flat, w3) + b3)
            #addSummaries(w3, summaries, "dense_layer", "mean_stddev_hist")
            #addSummaries(b3, summaries, "dense_layer", "mean_stddev_hist")
        #dropout
        h1_dropout = tf.nn.dropout(h1, p_dropout)
        #readout layer
        with tf.name_scope("readout_layer"):
            w4 = createWeights([1024, 2])
            b4 = createBiases([2])
            y  = tf.nn.softmax(tf.matmul(h1_dropout, w4) + b4)
        #cost
        with tf.name_scope("cost"):
            cost = tf.reduce_mean(
                -tf.reduce_sum(y_ * tf.log(tf.clip_by_value(y,1e-10,1.0)),
                reduction_indices=[1])
            )
            addSummaries(cost, summaries, "cost", "mean")
        #optimizer
        with tf.name_scope("train"):
            train = tf.train.AdamOptimizer().minimize(cost)
        #metrics
        with tf.name_scope("metrics"):
            y_pred  = tf.greater(tf.slice(y,  [0, 0], [-1, 1]), tf.slice(y,  [0, 1], [-1, 1]))
            y2_pred = tf.greater(tf.slice(y_, [0, 0], [-1, 1]), tf.slice(y_, [0, 1], [-1, 1]))
            correctness = tf.equal(y_pred, y2_pred)
            #accuracy
            accuracy = tf.reduce_mean(tf.cast(correctness, tf.float32))
            addSummaries(accuracy, summaries, "accuracy", "mean")
            #precision and recall
            truePos = tf.reduce_sum(tf.cast(
                tf.logical_and(correctness, tf.equal(y_pred, tf.constant(True))),
                tf.float32
            ))
            predPos = tf.reduce_sum(tf.cast(y_pred, tf.float32))
            actualPos = tf.reduce_sum(tf.cast(y2_pred, tf.float32))
            prec = tf.cond(
                tf.equal(predPos, tf.constant(0.0)),
                lambda: tf.constant(0.0),
                lambda: truePos / predPos
            )
            rec  = tf.cond(
                tf.equal(actualPos, tf.constant(0.0)),
                lambda: tf.constant(0.0),
                lambda: truePos / actualPos
            )
            addSummaries(prec, summaries, "precision", "mean")
            addSummaries(rec, summaries, "recall", "mean")
    #return output nodes and trainer
    return Network(graph, x, y_, p_dropout, y, accuracy, prec, rec, train, summaries)

def addSummaries(node, summaries, name, method):
    """
        Used to create and attach summary nodes to "node".
        "method" specifies the kinds of summaries to add.
    """
    with tf.device("/cpu:0"):
        if method == "mean":
            summaries.append(tf.scalar_summary(name + "/mean", tf.reduce_mean(node)))
        elif method == "mean_stddev_hist":
            mean = tf.reduce_mean(node)
            summaries.append(tf.scalar_summary(name + "/mean", mean))
            summaries.append(tf.scalar_summary(name + "/stddev", tf.reduce_mean(tf.square(node-mean))))
            summaries.append(tf.histogram_summary(name, node))
        elif method == "image":
            MAX_NUM_IMAGES = 10
            summaries.append(tf.image_summary(name, node, MAX_NUM_IMAGES))

def trainNetwork(net, numSteps, prod, testProd, summaryDir, testSummaryDir, reinitialise, saveFile):
    TRAINING_LOG_PERIOD  = 50 #informative lines are printed after this many training steps
    TRAINING_SAVE_PERIOD = 1000 #save every N steps
    TRAINING_RUN_PERIOD  = 50 #save runtime metadata every N steps
    startTime = time.time()
    summaryWriter = tf.train.SummaryWriter(summaryDir, net.graph)
    testSummaryWriter = tf.train.SummaryWriter(testSummaryDir, net.graph)
    with tf.Session(graph=net.graph) as sess:
        saver = tf.train.Saver(tf.all_variables())
        #reinitialise or load values
        if reinitialise or not os.path.exists(saveFile):
            sess.run(tf.initialize_all_variables())
        else:
            saver.restore(sess, saveFile)
        #do training
        for step in range(numSteps):
            inputs, outputs = prod.getBatch(BATCH_SIZE)
            if step > 0 and step % TRAINING_RUN_PERIOD == 0: #occasionally save runtime metadata
                run_metadata = tf.RunMetadata()
                summary, _ = sess.run(
                    [net.summaries, net.train],
                    feed_dict={net.x: inputs, net.y_: outputs, net.p_dropout: 0.5},
                    options=tf.RunOptions(trace_level=tf.RunOptions.FULL_TRACE),
                    run_metadata=run_metadata
                )
                summaryWriter.add_run_metadata(run_metadata, "step%03d" % step)
            else:
                summary, _ = sess.run(
                    [net.summaries, net.train],
                    feed_dict={net.x: inputs, net.y_: outputs, net.p_dropout: 0.5}
                )
            summaryWriter.add_summary(summary, step)
            #occasionally print step and accuracy
            if step % TRAINING_LOG_PERIOD == 0 or step == numSteps-1:
                inputs, outputs = testProd.getBatch(BATCH_SIZE)
                acc, prec, rec = sess.run(
                    [net.accuracy, net.precision, net.recall],
                    feed_dict={net.x: inputs, net.y_: outputs, net.p_dropout: 1.0}
                )
                testSummaryWriter.add_summary(summary, step)
                rps = (outputs.argmax(1) == 0).sum() / len(outputs)
                    #num positive samples / num samples
                print(
                    "%7.2f secs - step %4d, accuracy %.2f, precision %.2f, recall %.2f, rps %.2f" %
                    (time.time() - startTime, step, acc, prec, rec, rps)
                )
            #occasionally save variable values
            if step > 0 and step % TRAINING_SAVE_PERIOD == 0:
                saver.save(sess, saveFile)
        saver.save(sess, saveFile)
        summaryWriter.close()

def testNetwork(net, numSteps, prod, summaryDir, reinitialise, saveFile):
    TESTING_LOG_PERIOD = 50
    TESTING_RUN_PERIOD = 50
    startTime = time.time()
    summaryWriter = tf.train.SummaryWriter(summaryDir, net.graph)
    metrics = [] #[[accuracy, precision, recall], ...]
    with tf.Session(graph=net.graph) as sess:
        #reinitialise or load values
        if reinitialise or not os.path.exists(saveFile):
            sess.run(tf.initialize_all_variables())
        else:
            tf.train.Saver(tf.all_variables()).restore(sess, saveFile)
        #do testing
        for step in range(numSteps):
            inputs, outputs = prod.getBatch(BATCH_SIZE)
            feedDict = {net.x: inputs, net.y_: outputs, net.p_dropout: 1.0}
            if step > 0 and step % TESTING_RUN_PERIOD == 0: #if saving runtime metadata
                run_metadata = tf.RunMetadata()
                summary, acc, prec, rec = sess.run(
                    [net.summaries, net.accuracy, net.precision, net.recall],
                    feed_dict=feedDict,
                    options=tf.RunOptions(trace_level=tf.RunOptions.FULL_TRACE),
                    run_metadata=run_metadata
                )
                summaryWriter.add_run_metadata(run_metadata, "step%03d" % step)
            else:
                summary, acc, prec, rec = sess.run(
                    [net.summaries, net.accuracy, net.precision, net.recall],
                    feed_dict=feedDict
                )
            metrics.append([acc, prec, rec])
            summaryWriter.add_summary(summary, step)
            if step % TESTING_LOG_PERIOD == 0:
                print(
                    "%7.2f secs - step %4d, accuracy %.2f, precision %.2f, recall %.2f" %
                    (time.time()-startTime, step, acc, prec, rec)
                )
    accs  = [m[0] for m in metrics]
    precs = [m[1] for m in metrics]
    recs  = [m[2] for m in metrics]
    print(
        "Averages: accuracy %.2f, precision %.2f, recall %.2f" %
        (sum(accs)/len(accs), sum(precs)/len(precs), sum(recs)/len(recs))
    )
    summaryWriter.close()

def runNetwork(net, imageData, results, reinitialise, saveFile):
    """ Run the network on cells of an image, inserting them into 'results'.
        Only runs on cells where results[i][j] is non-negative.
    """
    with tf.Session(graph=net.graph) as sess:
        #reinitialise or load values
        if reinitialise or not os.path.exists(saveFile):
            sess.run(tf.initialize_all_variables())
        else:
            tf.train.Saver(tf.all_variables()).restore(sess, saveFile)
        #run on each cell
        for i in range(IMG_SCALED_HEIGHT//INPUT_HEIGHT):
            for j in range(IMG_SCALED_WIDTH//INPUT_WIDTH):
                if results[i][j] >= 0:
                    out = net.y.eval(feed_dict={
                        net.x: imageData[:, INPUT_HEIGHT*i:INPUT_HEIGHT*(i+1), \
                            INPUT_WIDTH*j:INPUT_WIDTH*(j+1), :],
                        net.p_dropout: 1.0
                    })
                    results[i][j] = out[0][0]
