import logging
import os
import sys
from getpass import getpass
from PyQt4.QtGui import QApplication
from PyQt4.QtCore import QUrl, SIGNAL, QObject, pyqtSignal, pyqtSlot, pyqtProperty, QTimer
from PyQt4.QtWebKit import QWebPage, QWebView
from time import sleep


logging.basicConfig(level=logging.INFO)
log = logging.getLogger()


class Proxy(QObject):

    onLogin = pyqtSignal(bool)
    onEnterBlocked = pyqtSignal(bool)
    onUnban = pyqtSignal(bool)
    onUnbanConfirm = pyqtSignal(bool)

    @pyqtSlot(str, bool)
    def trigger(self, name, success):
        self._active = False
        getattr(self, name).emit(success)

    _active = False
    _expect_success = {}
    _expect_failed = {}
    _wait_reload = True

    def _get_active(self):
        return self._active

    def set_active(self, value):
        self._active = value

    active = pyqtProperty(bool, fget=_get_active)

    def _get_expect_success(self):
        return self._expect_success

    def set_expect_success(self, value):
        self._expect_success = value
        self._active = True

    expect_success = pyqtProperty('QVariantMap', fget=_get_expect_success)

    def _get_expect_failed(self):
        return self._expect_failed

    def set_expect_failed(self, value):
        self._expect_failed = value
        self._active = True

    expect_failed = pyqtProperty('QVariantMap', fget=_get_expect_failed)

    def _get_wait_reload(self):
        return self._wait_reload

    def set_wait_reload(self, value):
        self._wait_reload = value

    wait_reload = pyqtProperty(bool, fget=_get_wait_reload)

    def _get_username(self):
        return os.environ['FACEBOOK_USERNAME']

    username = pyqtProperty(str, fget=_get_username)

    def _get_password(self):
        return os.environ['FACEBOOK_PASSWORD']

    password = pyqtProperty(str, fget=_get_password)

    @pyqtSlot(str)
    def info(self, text):
        log.info(text)

    @pyqtSlot(str)
    def debug(self, text):
        log.debug(text)

    @pyqtSlot(str)
    def error(self, text):
        log.error(text)

    @pyqtSlot(str)
    def warn(self, text):
        log.warn(text)


class WebPage(QWebPage):
    def _javaScriptConsoleMessage(self, message, lineNumber, sourceID):
        sys.stderr.write('Javascript error at line number %d\n' % lineNumber)
        sys.stderr.write('%s\n' % message)
        sys.stderr.write('Source ID: %s\n' % sourceID)


class FacebookUnban(QApplication):
    def __init__(self, argv, show_window=True):
        super().__init__(argv)

        self.web_page = WebPage()
        st = self.web_page.settings()
        st.setAttribute(st.AutoLoadImages, False)

        self.web_view = QWebView()
        self.web_view.setPage(self.web_page)
        self.web_view.loadFinished.connect(self._on_load_finished)

        if show_window:
            self.web_view.show()

        #self.connect(self.web_view, SIGNAL('loadFinished(bool)'),
        #        self._on_load_finished)

        self.load_timer = QTimer()
        self.load_timer.timeout.connect(self._on_load_timeout)

        self.proxy = Proxy()

        self.proxy.onLogin.connect(self._do_login)
        self.proxy.onEnterBlocked.connect(self._do_enter_blocked)
        self.proxy.onUnban.connect(self._do_unban)
        self.proxy.onUnbanConfirm.connect(self._do_unban_confirm)

        self.proxy.set_expect_success({
            'path': '/',
            'selectorExists': 'form#login_form',
            'trigger': 'onLogin'})
        self._start_load_timer()


    def _start_load_timer(self):
        self.load_timer.start(300000)


    def _on_load_timeout(self):
        log.warn('TIMEOUT')
        self.web_page.triggerAction(QWebPage.Stop)


    def _on_load_finished(self, ok):
        log.info('DOM Content Loaded')
        self.proxy.set_wait_reload(False)
        self.frame = self.web_page.currentFrame()
        self.frame.addToJavaScriptWindowObject('bot', self.proxy)
        self.frame.evaluateJavaScript("""
            (function()
            {
                function activate_expectation(expect, isSuccess) {

                    if (expect.trigger)
                    {
                        bot.trigger(expect.trigger, isSuccess);
                    }
                }

                function process_expectation(expect, isSuccess) {
                    if (expect.path)
                    {
                        bot.debug(expect.trigger);
                        bot.debug('"' + expect.path + '" :: "' + document.location.pathname + '"');
                    }

                    if (expect.path.match(document.location.pathname))
                    {
                        if (expect.selectorNotExists && document.querySelector(expect.selectorNotExists))
                        {
                            bot.debug('selectorNotExists: ' + expect.selectorNotExists);
                            return;
                        }
                        if (expect.selectorExists && !document.querySelector(expect.selectorExists))
                        {
                            bot.debug('selectorExists: ' + expect.selectorExists);
                            return;
                        }

                        bot.info('expectation achieved');
                        activate_expectation(expect, isSuccess);
                    }
                }

                setInterval(function()
                {
                    if (!bot.active || bot.wait_reload) { return; }

                    bot.debug('current path: ' + document.location.pathname);

                    process_expectation(bot.expect_success, true);
                    process_expectation(bot.expect_failed, false);
                }, 3000);

                window.fnClickElement = function(el)
                {
                    if (el.click)
                    {
                        el.click();
                    }
                    else
                    {
                        var evt = document.createEvent('MouseEvents');
                        evt.initMouseEvent('click', true, true, window, 0, 0, 0, 0, 0, false, false, false, false, 0, null);
                        el.dispatchEvent(evt);
                    }
                };

            }());
        """)


    def start(self):
        self.web_page.currentFrame().load(QUrl(self.home_url))


    def _do_login(self, bool):
        self.proxy.set_wait_reload(True)
        self.frame.evaluateJavaScript("""
            document.forms.login_form.querySelector('[name="email"]').value = bot.username;
            document.forms.login_form.querySelector('[name="pass"]').value = bot.password;
            document.forms.login_form.querySelector('input[type="submit"]').click();
        """)
        self._start_load_timer()
        self.proxy.set_expect_success({
            'path': '/',
            'selectorExists': 'div[data-click="profile_icon"]',
            'trigger': 'onEnterBlocked'})


    def _do_enter_blocked(self, bool):
        self.proxy.set_wait_reload(True)
        self.frame.evaluateJavaScript('document.location.href="' + self.home_url + self.forum_path + '/blocked/"')
        self._start_load_timer()
        self.proxy.set_expect_success({
            'path': self.forum_path + '/blocked/?',
            'selectorExists': '#pagelet_group_blocked div[id^="member_"] .adminActions > a[ajaxify*="action=remove_block"]',
            'trigger': 'onUnban'
        })


    def _do_unban(self, bool):
        sleep(3)
        self.frame.evaluateJavaScript("""
            var el = document.querySelector('#pagelet_group_blocked div[id^="member_"] .adminActions > a[ajaxify*="action=remove_block"]');
            fnClickElement(el);
        """)
        self.proxy.set_expect_success({
            'path': self.forum_path + '/blocked/?',
            'selectorExists': 'button[name="remove_block"]',
            'trigger': 'onUnbanConfirm',
        })


    def _do_unban_confirm(self, bool):
        self.proxy.set_wait_reload(True)
        self.frame.evaluateJavaScript("""
            document.querySelector('button[name="remove_block"]').click();
        """)
        self._start_load_timer()
        self.proxy.set_expect_success({
            'path': self.forum_path + '/blocked/?',
            'selectorExists': '#pagelet_group_blocked div[id^="member_"] .adminActions > a[ajaxify*="action=remove_block"]',
            'trigger': 'onUnban',
        })


if __name__ == '__main__':
    if not 'FACEBOOK_USERNAME' in os.environ:
        os.environ['FACEBOOK_USERNAME'] = input('Enter Facebook username (email): ')
    if not 'FACEBOOK_PASSWORD' in os.environ:
        os.environ['FACEBOOK_PASSWORD'] = getpass('Enter Facebook password: ')

    forum_url_name = input('Enter Facebook forum name (e.g just sencha.indo.admin from /groups/sencha.indo.admin): ')

    bot = FacebookUnban(sys.argv)
    bot.home_url = 'https://www.facebook.com'
    bot.forum_path = '/groups/' + forum_url_name
    bot.start()

    sys.exit(bot.exec_())
