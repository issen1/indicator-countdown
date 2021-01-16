#!/usr/bin/python

import errno, json, os, os.path, sys, time
from datetime import datetime, timedelta
import signal
import gi
gi.require_version('Gtk', '3.0')
gi.require_version('AppIndicator3', '0.1')
from gi.repository import Gtk, GLib
from gi.repository import AppIndicator3 as appindicator


ENABLE_AUTOSTART = os.path.abspath(os.path.join(os.path.dirname(os.path.realpath(__file__)), 'enable-autostart.sh'))
DISABLE_AUTOSTART = os.path.abspath(os.path.join(os.path.dirname(os.path.realpath(__file__)), 'disable-autostart.sh'))
ICONPATH = os.path.abspath(os.path.join(os.path.dirname(os.path.realpath(__file__)), 'icons'))
CONFIGPATH = os.path.join(os.path.expanduser('~'), '.config', 'jh-indicator-countdown', 'indicator-countdown.config')


def show_dialog(msgtype, title, text):
  # Gtk.MessageType.ERROR, Gtk.MessageType.INFO, Gtk.MessageType.WARNING, Gtk.MessageType.QUESTION
  dialog = Gtk.MessageDialog(None, 0, msgtype, Gtk.ButtonsType.CLOSE, title)
  dialog.format_secondary_text(text)
  dialog.run()
  dialog.destroy()


class Config:
  def __init__(self):
    self.config_status = 'normal'   # normal, error_reading or first_run
    self.timestamp = int(time.time() + 3600)
    self.event_name = 'Default'
    self.format_str = "Countdown: {%}"
    self.icon = 'watch-normal.svg'
    self.icon_attention = 'watch-attention.svg'
    self.attention_diff = 120
    self.autostart = False

    if not os.path.isfile(CONFIGPATH):
      self.config_status = 'first_run'
      return

    try:
      with open(CONFIGPATH) as configFile:
        data = json.load(configFile)
        self.check(data)

        self.timestamp = int(data['timestamp'])
        self.format_str = data['format_str']
        self.icon = data['icon']
        self.icon_attention = data['icon_attention']
        self.attention_diff = data['attention_diff']
        self.autostart = data['autostart']
        self.event_name = data['event_name']
    except KeyError as ex:
      print repr(ex)
      self.config_status = 'error_reading'


  def check(self, values):
    try:
      return \
        (values['timestamp'] > int(time.time()) and
        os.path.isfile(os.path.join(ICONPATH, values['icon'])) and
        os.path.isfile(os.path.join(ICONPATH, values['icon_attention'])) and
        '{%}' in values['format_str'])
    except:
      return False

  def set_all(self, values):
    if not self.check(values): return False
    self.timestamp = values['timestamp']
    self.event_name = values['event_name']
    self.format_str = values['format_str']
    self.icon = values['icon']
    self.icon_attention = values['icon_attention']
    self.attention_diff = values['attention_diff']
    self.autostart = values['autostart']
    return True

  def save(self):
    # Create dirs safely
    configdir = os.path.dirname(CONFIGPATH)
    try:
      os.makedirs(configdir)
    except OSError as err:  # Python >2.5
      if err.errno == errno.EEXIST and os.path.isdir(configdir):
        pass
      else:
        raise

    # Writing our configuration file 
    with open(CONFIGPATH, 'wb') as configFile:
        json.dump(self.__dict__, configFile)

    return True


class Indicator:
  def __init__(self, config):
    self.config = config
    self.quit = False
    self.UPDATE_INTERVAL = 2

    self.ind = appindicator.Indicator.new_with_path(
                          "indicator-countdown",
                          os.path.splitext(self.config.icon)[0],
                          appindicator.IndicatorCategory.APPLICATION_STATUS,
                          ICONPATH)
    self.ind.set_status(appindicator.IndicatorStatus.ACTIVE)
    self.ind.set_attention_icon(os.path.splitext(self.config.icon_attention)[0])
    
    self.build_menu()

    self.ind.set_menu(self.menu)
    
    self.update_time()
    GLib.timeout_add_seconds(self.UPDATE_INTERVAL, self.update_time)


  def update_time(self):
    # return false to stop timer
    if self.quit: return False
    diff_seconds = self.config.timestamp-int(time.time())
    diff_timedelta = timedelta(seconds=diff_seconds)
    self.ind.set_label(self.config.format_str.replace("{%}", str(diff_timedelta)), "100%")
    if diff_seconds < self.config.attention_diff * 60:
      self.ind.set_status(appindicator.IndicatorStatus.ATTENTION)
    else:
      self.ind.set_status(appindicator.IndicatorStatus.ACTIVE)
    return True


  def menu_handler_countdown(self, source):
    if show_settings_dialog(self.config):
      self.ind.set_icon(os.path.splitext(self.config.icon)[0])
      self.ind.set_attention_icon(os.path.splitext(self.config.icon_attention)[0])
      self.menu_item_countdown.set_label("Setup %s..." % self.config.event_name)
      self.update_time()

  def quit_app(self, source):
    self.quit = True
    Gtk.main_quit()

  def build_menu(self):
    self.menu = Gtk.Menu()

    self.menu_item_countdown = Gtk.MenuItem("Setup %s..." % self.config.event_name)
    self.menu_item_countdown.connect("activate", self.menu_handler_countdown)
    self.menu.append(self.menu_item_countdown)

    self.menu_item_quit = Gtk.MenuItem("Quit")
    self.menu_item_quit.connect("activate", self.quit_app)
    self.menu.append(self.menu_item_quit)

    self.menu.show_all()


class SettingsDialog(Gtk.Dialog):

  def __init__(self, config):
    Gtk.Dialog.__init__(self, "Settings", None, 0,
        (Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL,
         Gtk.STOCK_APPLY, Gtk.ResponseType.APPLY))

    self.set_default_size(150, 100)

    self.config = config

    # complictated datetime picker layout
    self.hbox_datetime = Gtk.HBox(homogeneous=False, spacing=2)
    # time range obviously a little buggy, since time is continuing to run during dialog
    current_time = int(time.time())
    max_time = current_time + 31557600   # one year
    current_value = max(current_time, min(self.config.timestamp, max_time))
    self.entry_timestamp = Gtk.SpinButton(numeric=True,
      adjustment=Gtk.Adjustment.new(current_value, current_time, max_time, 1800, 86400, 86400))
    self.hbox_datetime.add(self.entry_timestamp)
    self.hbox_picker_button = Gtk.Button.new_from_icon_name(Gtk.STOCK_INDEX, Gtk.IconSize.BUTTON)
    self.hbox_picker_button.connect("clicked", self.picker_handler)
    self.hbox_datetime.pack_start(self.hbox_picker_button, False, False, 0)

    # other entries
    self.entry_event_name = Gtk.Entry(text=self.config.event_name)
    self.entry_format_str = Gtk.Entry(text=self.config.format_str)
    self.entry_custom_icon = Gtk.Entry(text=self.config.icon)
    self.entry_custom_icon_attention = Gtk.Entry(text=self.config.icon_attention)
    self.entry_autostart = Gtk.CheckButton(label='Autostart', active=self.config.autostart)
    self.entry_attention_diff = Gtk.SpinButton(numeric=True,
      adjustment=Gtk.Adjustment.new(self.config.attention_diff, 1, 50000, 5, 60, 60))

    # Structure & Layout
    box = self.get_content_area()

    box.add(Gtk.Label("The name of this Countdown"))
    box.add(self.entry_event_name)
    box.add(Gtk.Label()) # spacer

    box.add(Gtk.Label("The UNIX timestamp when this happens"))
    box.add(self.hbox_datetime)
    box.add(Gtk.Label()) # spacer

    box.add(Gtk.Label("The format string for the indicator"))
    box.add(self.entry_format_str)
    box.add(Gtk.Label()) # spacer

    box.add(Gtk.Label("The default icon for this event"))
    box.add(self.entry_custom_icon)
    box.add(Gtk.Label()) # spacer

    box.add(Gtk.Label("The attention icon for this event"))
    box.add(self.entry_custom_icon_attention)
    box.add(Gtk.Label()) # spacer

    box.add(Gtk.Label("When attention should be enabled in minutes before event"))
    box.add(self.entry_attention_diff)
    box.add(Gtk.Label()) # spacer

    box.add(self.entry_autostart)
    box.add(Gtk.Label()) # spacer

    self.show_all()


  def picker_handler(self, source):
    dialog = DateTimeDialog(self.config)
    response = dialog.run()
    try:
      if response == Gtk.ResponseType.APPLY:
        year, month, day = dialog.calendar.get_date()
        hours = int(dialog.hours.get_value())
        minutes = int(dialog.minutes.get_value())
        seconds = int(dialog.seconds.get_value())

        dt = datetime(year, month+1, day, hours, minutes, seconds)
        self.entry_timestamp.set_value( (dt - datetime(1970, 1, 1)).total_seconds() )

    except ValueError as ex:
      show_dialog(Gtk.MessageType.ERROR, "Error in your values.", "An error occured applying your datetime values. They are not saved.")
      print repr(ex)

    finally:
      dialog.destroy()

class DateTimeDialog(Gtk.Dialog):
  """ would be nice to have timezone aware datetime picker...
      for now it is UTC based and you have to manually calculate
      your local time -- sorry folks """

  def __init__(self, config):
    Gtk.Dialog.__init__(self, "Pick Date and Time", None, 0,
        (Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL,
         Gtk.STOCK_APPLY, Gtk.ResponseType.APPLY))

    self.set_default_size(200, 120)
    self.DEF_PAD = 4
    self.DEF_PAD_SMALL = 2

    vbox = self.get_content_area()

    # Calendar widget
    self.calendar = Gtk.Calendar()
    separator = Gtk.HSeparator()

    # Time widget
    self.hbox = Gtk.HBox(homogeneous=True, spacing=1)

    # hour, minutes and seconds
    self.hours = Gtk.SpinButton(numeric=True,
      adjustment=Gtk.Adjustment.new(12, 0, 24, 1, 1, 1))
    self.minutes = Gtk.SpinButton(numeric=True,
      adjustment=Gtk.Adjustment.new(0, 0, 60, 1, 1, 1))
    self.seconds = Gtk.SpinButton(numeric=True,
      adjustment=Gtk.Adjustment.new(0, 0, 60, 1, 1, 1))

    self.hbox.add(self.hours)
    self.hbox.add(self.minutes)
    self.hbox.add(self.seconds)

    vbox.add(Gtk.Label("The day"))
    vbox.add(self.calendar)
    vbox.pack_start(separator, False, True, 0)
    vbox.add(Gtk.Label("")) # spacer
    vbox.add(Gtk.Label("Hours, minutes and seconds"))
    vbox.add(self.hbox)
    self.show_all()


def toggle_autostart(autostart):
  if autostart:
    os.system("sh %s" % ENABLE_AUTOSTART)
  else:
    os.system("sh %s" % DISABLE_AUTOSTART)


def show_settings_dialog(config):
  dialog = SettingsDialog(config)
  response = dialog.run()
  try:
    if response == Gtk.ResponseType.APPLY:    
      # set values in config
      config_values = {
        'timestamp': int(dialog.entry_timestamp.get_text()),
        'event_name': dialog.entry_event_name.get_text(),
        'format_str': dialog.entry_format_str.get_text(),
        'icon': dialog.entry_custom_icon.get_text(),   
        'icon_attention': dialog.entry_custom_icon_attention.get_text(),
        'attention_diff': dialog.entry_attention_diff.get_value(),
        'autostart': dialog.entry_autostart.get_active()
      }

      if not config.set_all(config_values):
        show_dialog(Gtk.MessageType.ERROR, "Error valddating Config.", "An error occured while saving the config file. Please check your config.")
        return False

      if not config.save():
        show_dialog(Gtk.MessageType.ERROR, "Error saving Config.", "An error occured while saving the config file. Please check your filesystem.")
        return False

      toggle_autostart(config.autostart)

      return True
    else:
      return False
  finally:
    dialog.destroy()



if __name__ == "__main__":
  config = Config()

  if config.config_status == 'first_run':
    show_dialog(Gtk.MessageType.INFO, 'First start of Countdown', 'This seems to be your first start of this indicator, please set your preferences.')
    if not show_settings_dialog(config):
      sys.exit()
  elif config.config_status == 'error_reading':
    show_dialog(Gtk.MessageType.ERROR, "Error reading config file.", "An error occured reading the config file. Using default values instead.")
    if not show_settings_dialog(config):
      sys.exit()

  indicator = Indicator(config)

  signal.signal(signal.SIGINT, signal.SIG_DFL) # for stopping
  Gtk.main()
