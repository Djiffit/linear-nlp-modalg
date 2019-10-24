import csv
import sys
import os
import re

from collections import defaultdict as dd

import numpy as np

UDHEADER=["ID","FORM","LEMMA","UPOS","XPOS","FEATS","HEAD","DEPREL","DEPS",
          "MISC"]
SEMEVALHEADER = ['ID','SENTIMENT','BODY']
LANGUAGES = "finnish german spanish".split(" ")

def read_conllu(filename):
    """ 
    Read a CoNLL-U file from @filename into a list of sentences. Each
    sentence is a list of tokens. Each token is a dictionary with
    keys:

      ID     - ID number of the token in the sentence.
      FORM   - Orthographic representation of the token, e.g. "cats".
      LEMMA  - The lemma, e.g. "cat".
      UPOS   - The Universal Dependencies 2.0 POS tag.
      XPOS   - Language specific POS tag.
      FEATS  - Morphological features.
      HEAD   - The id of the head word of this token (0 if this is 
               the head of the sentence).
      DEPREL - The dependency label between this word and its head 
               ('root' if this is the head of the sentence).
      DEPS   - Enhanced dependencies.
      MISC   - Other annotations.

      For example,

      {'ID': '1', 'FORM': 'Al', 'LEMMA': 'Al', 'UPOS': 'PROPN', 'XPOS': 'NNP', 
       'FEATS': 'Number=Sing', 'HEAD': '0', 'DEPREL': 'root', 'DEPS': '_', 
       'MISC': 'SpaceAfter=No'}
    """
    data = [[]]

    with open(filename,encoding="utf-8") as udfile:
        csvreader = csv.reader(filter(lambda x:x == '' or x[0]!='#', udfile),
                               delimiter='\t',
                               quoting=csv.QUOTE_NONE)
        for i, fields in enumerate(csvreader):
            if fields and len(fields) != len(UDHEADER):
                raise SyntaxError('Incorrect field count', 
                                  (filename, i, None, None)) 
            if fields == []:
                data.append([])
            else:
                data[-1].append(dict(zip(UDHEADER,fields)))

    return data
                    
def read_semeval(filename):
    """
    Read a list of tweets with sentiment labels from @sefilename. Each
    tweet is a dictionary with keys:
 
    ID        - ID number of tweet.
    SENTIMENT - Sentiment label for this tweet.
    BODY      - List of tokens of this tweet.

    """
    data = []

    with open(filename,encoding="utf-8") as sefile:
        csvreader = csv.reader(sefile, delimiter='\t', quoting=csv.QUOTE_NONE)
        for i, fields in enumerate(csvreader):
            if fields and len(fields) != len(SEMEVALHEADER):
                raise SyntaxError('Incorrect field count', 
                                  (filename, i, None, None)) 
            tweet = dict(zip(SEMEVALHEADER,fields))
            tweet['ORIG_BODY'] = tweet['BODY']
            data.append(tweet)
    return data

def read_semeval_datasets(data_dir):
    data = {}
    for data_set in ["training","development.input","development.gold",
                     "test.input","test.gold"]:
        data[data_set] = read_semeval(os.path.join(data_dir,"%s.txt" % data_set)) 
    return data

def read_20newsgroup_datasets(data_dir):
    data = {}
    for fn in ["train","test"]:
        data[fn] = []
        for line in open(os.path.join(data_dir,"20_ng_train.data"),encoding='utf-8'):
            line = line.strip('\n')
            if line:
                doc_id,feature,count = line.split(' ')
                doc_id = int(doc_id)
                count = int(count)
                if len(data[fn]) < doc_id:
                    data[fn].append({})
                    data[fn][-1]["BODY"] = []
                data[fn][doc_id - 1]["BODY"] += count * [feature]
        for i,line in enumerate(open(os.path.join(data_dir,"20_ng_train.label"),
                                     encoding='utf-8')):
            line = line.strip('\n')
            if line:
                data[fn][i]["CLASS"] = line

        data[fn] = [ex for ex in data[fn] if int(ex["CLASS"]) < 4]

    return data

def read_sigmorphon_train(data_dir,lan):
    data = []
    output_characters = set()
    for line in open(os.path.join(data_dir,"%s-task1-train" % lan), encoding='utf-8'):
        line = line.strip()
        if line != '':
            m = re.match("^(.*)\t(.*)\t(.*)\t(.*)$",line)
            data.append({})
            data[-1]["WF"], data[-1]["TAG"], data[-1]["LEMMA"], \
                data[-1]["ALIGNED_LEMMA"] = m.groups()             
            data[-1]["WF"] = [c for c in data[-1]["WF"]]
            data[-1]["TAG"] = {f:v for f,v in [x.split('=') 
                                               for x in data[-1]["TAG"].split(",")]}
            data[-1]["ALIGNED_LEMMA"] = data[-1]["ALIGNED_LEMMA"].split(",")
            output_characters.update(data[-1]["ALIGNED_LEMMA"])
    return data, list(sorted(output_characters))

def read_sigmorphon_dev_and_test(data_dir,lan):
    results = []
    for split in "dev test".split(" "):
        data = []
        for line in open(os.path.join(data_dir,"%s-task1-%s" % (lan, split)),
                encoding='utf-8'):
            line = line.strip()
            if line != "":
                wf, tag, lemma = line.split("\t")
                tag = {f:v for f,v in [x.split('=') 
                                       for x in tag.split(",")]}
                data.append({"LEMMA":lemma,
                             "TAG":tag,
                             "WF":[c for c in wf]})
        results.append(data)
    return results

def read_sigmorphon(data_dir,use_mini_data):
    data = {}
    for lan in LANGUAGES:
        data[lan] = {}
        data[lan]["train"], data[lan]["output_characters"] = \
            read_sigmorphon_train(data_dir,lan)
        if use_mini_data:
            data[lan]["train"] = data[lan]["train"][:1000]
        data[lan]["development"], data[lan]["test"] = \
            read_sigmorphon_dev_and_test(data_dir,lan)
    return data 

def evaluate(sys_classes, gold_data):
    classes = set(sys_classes + [ex["CLASS"] for ex in gold_data])
    cgncy_table = {(c1,c2):0 for c1 in classes for c2 in classes}
    gold_table = {c:0 for c in classes}
    sys_table = {c:0 for c in classes}

    for sys_c, gold_ex in zip(sys_classes,gold_data):
        gold_c = gold_ex["CLASS"]
        cgncy_table[(sys_c,gold_c)] += 1
        gold_table[gold_c] += 1
        sys_table[sys_c] += 1
        
    fscores = {}

    for c in classes:        
        c_recall = (cgncy_table[(c,c)] * 1.0 / gold_table[c] 
                    if gold_table[c] > 0
                    else 0)
        c_precision = (cgncy_table[(c,c)] * 1.0 / sys_table[c]
                       if sys_table[c] > 0
                       else 0)
        fscores[c] = (200 * (c_recall * c_precision) / (c_recall + c_precision)
                      if c_recall + c_precision > 0
                      else 0)
                      
    accuracy = (sum([cgncy_table[(c,c)] for c in classes]) * 100.0 / 
                len(sys_classes))

    return accuracy, fscores

def write_semeval(data,output,output_file):
    for ex, klass in zip(data,output):
        print("%s\t%s\t%s" % (ex["ID"], klass, ex["ORIG_BODY"]),
              file=output_file)

def write_conll_ner(output,data,results_dir):
    output_file = open(os.path.join(results_dir,"test.output.txt"),"w",
                       encoding="utf-8")
    for ex, classes in zip(data,output):
        for i, token in enumerate(ex["TOKENS"]):
            print("%s %s %s %s" % (token, ex["POS TAGS"][i], ex["CHUNKS"][i], 
                                   classes[i]),
                  file=output_file)
        print('',file=output_file)

def write_sigmorphon(output,data,results_dir,language,split):
    output_file = open(os.path.join(results_dir,"%s-task1-%s.sys" % 
                                    (language,split)),
                       "w",encoding="utf-8")
    for ex, output in zip(data,output):
        output = ''.join([s for s in output if s != '_'])    
        wf = ''.join([s for s in ex["WF"] if s != '_'])    
        tag = ','.join(['%s=%s' % (k,v) for k,v in ex["TAG"].items()])
        print("\t".join([output,tag,wf]),file=output_file)

def get_class(distribution):
    return list(distribution.keys())[np.argmax(list(distribution.values()))]

def read_conll_ner(data_dir):
    data = {}
    train_vocab = set()
    train_tags = set()
    train_pos_tags = set()

    for fn in ["train","development","test"]:
        data[fn] = [{"TOKENS":[], "POS TAGS":[], "CHUNKS":[], "TAGS":[]}]
        for line in open(os.path.join(data_dir,"%s.txt" % fn),encoding='utf-8'):
            line = line.strip('\n')
            if not line:
                data[fn].append({"TOKENS":[], "POS TAGS":[], "CHUNKS":[], "TAGS":[]})
            else:
                wf, pos, chunk, ner = line.split(' ')
                data[fn][-1]["TOKENS"].append(wf)
                data[fn][-1]["POS TAGS"].append(pos)
                data[fn][-1]["CHUNKS"].append(chunk)
                data[fn][-1]["TAGS"].append(ner)

                if fn == "train":
                    train_vocab.add(wf)
                    train_tags.add(ner)
                    train_pos_tags.add(pos)
        data[fn] = [s for s in data[fn] if s["TOKENS"] != []]
    return data, sorted(list(train_vocab)), sorted(list(train_tags)), \
        sorted(list(train_pos_tags))

def read_gazetteers(data_dir):
    gazetteers = {}
    
    for fn in ["geographical","organization","person_name"]:
        path = os.path.join(data_dir,"%s_words" % fn)
        gazetteers[fn] = {entry 
                          for entry in open(path).read().split('\n') 
                          if entry != ''}

    return gazetteers

def get_ranges(l):
    elements = []
    current_element = None
    current_start = None
    for i,ll in enumerate(l):
        if ll == 'O':
            if current_element != None:
                elements.append((current_element,current_start,i))
            current_element = None
            current_start = -1
        elif ll[0] == 'B':
            if current_element != None:
                elements.append((current_element,current_start,i))
            current_element = ll[2:]
            current_start = i
        elif ll[0] == "I":
            if current_element != ll[2:]:
                elements.append((current_element,current_start,i))
                current_element = ll[2:]
                current_start = i
    return elements

def eval_ner(labels,data_set):
    tp, fp, fn = 0.0, 0.0, 0.0
    for ls, ex in zip(labels,data_set):
        sys_ranges = get_ranges(ls)
        gold_ranges = get_ranges(ex["TAGS"])
        for r in sys_ranges:
            if r in gold_ranges:
                tp += 1
            else:
                fp += 1
        for r in gold_ranges:
            if not r in sys_ranges:
                fn += 1
    recall = 0
    if tp + fn > 0:
        recall = tp / (tp + fn)
    prec = 0
    if tp + fp > 0:
        prec = tp / (tp + fp)
    if recall + prec == 0:
        return 0, 0, 0
    else:
        return recall, prec, 2 * recall * prec / (recall + prec)

def eval_lemmatizer(sys_data,gold_data,distance):
    matching = 0
    edit_dist = 0
    for sys_lemma, gold_example in zip(sys_data,gold_data):
        sys_lemma = ''.join([s for s in sys_lemma if s != '_'])
        gold_lemma = gold_example["LEMMA"]
        matching += sys_lemma == gold_lemma
        edit_dist += distance(sys_lemma, gold_lemma)
    return matching * 1.0 / len(sys_data), edit_dist * 1.0 / len(sys_data)

if __name__=="__main__":
    # Check that we don't crash on reading.
    read_semeval('%s/semeval/training.txt' % sys.argv[1])
    read_semeval('%s/semeval/development.input.txt' % sys.argv[1])
    read_semeval('%s/semeval/development.gold.txt' % sys.argv[1])
    read_semeval('%s/semeval/test.input.txt' % sys.argv[1])
    read_semeval('%s/semeval/test.gold.txt' % sys.argv[1])

    read_conllu('%s/ud/en-ud-train.txt' % sys.argv[1])
    read_conllu('%s/ud/en-ud-dev.input.txt' % sys.argv[1])
    read_conllu('%s/ud/en-ud-dev.gold.txt' % sys.argv[1])
    read_conllu('%s/ud/en-ud-test.input.txt' % sys.argv[1])
    read_conllu('%s/ud/en-ud-test.gold.txt' % sys.argv[1])

