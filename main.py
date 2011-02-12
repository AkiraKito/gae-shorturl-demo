# coding: utf-8

from google.appengine.ext import webapp
from google.appengine.ext.webapp import util, template

from google.appengine.ext import db
from google.appengine.ext.db import TransactionFailedError
from google.appengine.api import memcache

import os
from uuid import uuid4


csrf_token_ns = 'csrf'


def int_to_alnum(num):
	"""int to alnum conversion"""
	result = ''
	if num == 0: return 'a'
	while num:
		code = num % 62
		num /= 62
		if code < 26:
			code = ord('a') + code	# offset from 'a'
		elif code < 52:
			code = ord('A') + (code - 26)
		else:
			code = ord('0') + (code - 52)
		result = chr(code) + result
	return result



class URLCounter(db.Model):
    count = db.IntegerProperty(default=0)

    def __new__(cls, *args, **kwargs):
        cls._cache_key = '__%s__' % cls.__name__
        return super(URLCounter, cls).__new__(cls, *args, **kwargs)


    @classmethod
    def next(cls):
        def incr(key):
            counter = db.get(key)
            counter.count = counter.count + 1
            db.put(counter)
        
        counter = cls.all().get()
        if counter is None:
            counter = cls()
            counter.put()
        try:
            db.run_in_transaction(incr, counter.key())
        except TransactionFailedError:
            pass
        memcache.set(cls._cache_key, counter.count)
        return int_to_alnum(counter.count)


    @classmethod
    def get(cls, is_alnum=False):
        count = memcache.get(cls._cache_key)
        if count is None:
            counter = cls.all().get()
            if counter is None: # missing model entity
                counter = cls(count=0)
                try:
                    db.run_in_transaction(counter.put)
                except TransactionFailedError:
                    pass
            count = counter.count
            memcache.set(cls._cache_key, count)
        if is_alnum:
            return int_to_alnum(count)
        return count



class URLModel(db.Model):
    url_id = db.StringProperty(required=True)
    url    = db.TextProperty(required=True)
    date   = db.DateTimeProperty(auto_now_add=True)



class MainHanlder(webapp.RequestHandler):
    def get(self):
        csrf_token = uuid4().hex
        memcache.set(csrf_token, True, time=1200, namespace=csrf_token_ns)

        path = os.path.join(os.path.dirname(__file__), 'home.html')
        self.response.out.write(template.render(path,
                                                {'csrf_token': csrf_token}))


    def post(self):
        # CSRF check
        csrf_token = self.request.get('_x', default_value='')
        if not csrf_token:
            self.response.set_status(404)
            return
        if not memcache.get(csrf_token, namespace=csrf_token_ns):
            self.response.set_status(404)
            return
        memcache.delete(csrf_token, namespace=csrf_token_ns)

        # URL check
        shorten_url = self.request.get('shorten_url', default_value=None)
        if shorten_url is None:
            self.response.set_status(400)   # Bad Request
            return

        # URL is not exist?
        url = URLModel.all().filter('url_id =', shorten_url).get()
        if url is None:
            # shorten!
            url = URLModel(url_id=URLCounter.next(),
                           url=shorten_url)
            url.put()

        # make short url
        short_url = self.request.host_url + '/' + url.url_id

        # response
        path = os.path.join(os.path.dirname(__file__), 'home.html')
        self.response.out.write(template.render(path,
                                                {'short_url': short_url}))



class URLShortcutHandler(webapp.RequestHandler):
    def get(self, url_id):
        self.response.out.write('mainhandler! %s' % url_id)
        url = URLModel.all().filter('url_id =', url_id).get()
        if url is None:
            self.response.set_status(404)
            return
        self.redirect(url.url)



def main():
    application = webapp.WSGIApplication([('/', MainHanlder),
                                          ('^/([A-Za-z0-9]+)$', URLShortcutHandler)],
                                         debug=True)
    util.run_wsgi_app(application)


if __name__ == '__main__':
    main()
