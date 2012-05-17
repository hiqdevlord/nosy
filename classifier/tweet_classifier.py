import multiprocessing
import simplejson
import redis
import random
import sys

from nosy.model import ClassifiedObject
import nosy.util
from nosy.stream_handler import TwitterHandler
from nosy.algorithm.lang import LanguageClassifier
from nosy.algorithm.naive_bayes import NaiveBayesClassifier

class ClassifierWorker(multiprocessing.Process):
    _redis = redis.Redis()
    THRESHOLDS_KEY = 'nosy:classify:thresholds'
    THRESHOLDS = { k: float(v) for k,v in _redis.hgetall(THRESHOLDS_KEY).iteritems() }
    NAIVE_BAYES = NaiveBayesClassifier.load()

    @classmethod
    def exceeds_thresholds(cls, c):
        for tag, confidence in c.tags.iteritems():
            if confidence < cls.THRESHOLDS.get(tag, 0):
                return False
        return True

    def __init__(self, harvester):
        super(ClassifierWorker, self).__init__()
        self.harvester = harvester

    @classmethod
    def publish(cls, class_obj):
        message = { 'channels' : ['nosy'], 'data' : class_obj.to_dict() }
        json = simplejson.dumps(message, default=nosy.util.json_serializer)
        cls._redis.publish('juggernaut', json)

    def run(self):
        while(True):            
            data = self.harvester.queue.get(True, timeout=120)

            try:
                c = self.harvester.to_classification_object(data)
            except KeyError:
                continue
            
            c.process()
            
            LanguageClassifier.classify(c)
            self.NAIVE_BAYES.classify(c)

            if (self.exceeds_thresholds(c)):
                self.publish(c)
                c.save()

class TweetClassifier(TwitterHandler):
    Worker = ClassifierWorker

    @classmethod
    def to_classification_object(cls, json):
        c = ClassifiedObject()
        
        c.source = 'twitter'
        c.text = json['text']
        c.created_at = json['created_at']
        c.author = json['user']['screen_name']
        c.location = json['geo'] or \
            { 
                'longitude' : 18 + random.random(),
                'latitude' : 59 + random.random()
            }

        return c    

if __name__ == "__main__":
    TweetClassifier.run()