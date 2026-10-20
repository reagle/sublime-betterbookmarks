import sublime, sublime_plugin, os, collections, json, hashlib

# Add our BetterBookmarks cache folder if it doesn't exist
def plugin_loaded():
   directory = '{:s}/User/BetterBookmarks'.format(sublime.packages_path())
   if not os.path.exists(directory):
      os.makedirs(directory)

# Views whose marks were read from the cache during this plugin session.
Loaded = set()

def Log(message):
   if Settings().get('verbose', False):
      print('[BetterBookmarks] ' + message)

def Settings():
    return sublime.load_settings('BetterBookmarks.sublime-settings')

def Variable(var, window=None):
   window = window if window else sublime.active_window()
   return sublime.expand_variables(var, window.extract_variables())

# Takes a region and converts it to a list taking into consideration if
#  the user wants us to care about the order of the selection.
def FixRegion(mark):
   if Settings().get("ignore_cursor", True):
      return [mark.begin(), mark.end()]
   return [mark.a, mark.b]

# Offsets go stale when the file is edited elsewhere (another machine, git, a
#  formatter), so each end of a mark is also stored as its line number, column,
#  and line text. The offsets stay first so older versions can still read marks.
def ToMark(view, mark):
   a, b = FixRegion(mark)
   return [a, b, ToAnchor(view, a), ToAnchor(view, b)]

def ToAnchor(view, point):
   row, col = view.rowcol(point)
   return {'line': row, 'col': col, 'text': view.substr(view.line(point))}

# Find the anchor's line: its old number if the text still matches there,
#  otherwise the nearest line with identical text, otherwise the old number.
def FromMark(view, lines, mark):
   if len(mark) < 4:
      return sublime.Region(min(mark[0], view.size()), min(mark[1], view.size()))
   return sublime.Region(FromAnchor(view, lines, mark[2]), FromAnchor(view, lines, mark[3]))

def FromAnchor(view, lines, anchor):
   row, text = anchor['line'], anchor['text']
   if not (row < len(lines) and lines[row] == text):
      matches = [i for i, line in enumerate(lines) if line == text]
      if matches:
         row = min(matches, key=lambda i: abs(i - row))
      else:
         row = min(row, len(lines) - 1)
   col = min(anchor['col'], len(lines[row]))
   return view.text_point(row, col)

class BetterBookmarksCommand(sublime_plugin.TextCommand):
   def __init__(self, edit):
      sublime_plugin.TextCommand.__init__(self, edit)
      self.filename = Variable('${file_name}')
      self.layers = None
      self.on_layer_setting_change()
      self.layer = Settings().get('default_layer')
      while not self.layers[0] == self.layer:
         self.layers.rotate(1)
      Settings().add_on_change('layer_icons', self.on_layer_setting_change)

   def on_layer_setting_change(self):
      self.layers = collections.deque(Settings().get('layer_icons'))

   def _is_empty(self):
      for layer in self.layers:
         if self.view.get_regions(self._get_region_name(layer)):
            return False

      return True

   # Get the path to the cache file.
   def _get_cache_filename(self):
      h = hashlib.md5()
      h.update(self.view.file_name().encode())
      filename = str(h.hexdigest())
      return '{:s}/User/BetterBookmarks/{:s}.bb_cache'.format(sublime.packages_path(), filename)

   def _get_region_name(self, layer=None):
      return 'better_bookmarks_{}'.format(layer if layer else self.layer)

   # Renders the current layers marks to the view
   def _render(self):
      marks = self.view.get_regions(self._get_region_name())
      icon = Settings().get('layer_icons')[self.layer]['icon']
      scope = Settings().get('layer_icons')[self.layer]['scope']

      self.view.add_regions('better_bookmarks', marks, scope, icon, sublime.PERSISTENT | sublime.HIDDEN)

   # Internal function for adding a list of marks to the existing ones.
   #  Any marks that exist in both lists will be removed as this case is when the user is 
   #     attempting to remove a mark.
   def _add_marks(self, newMarks, layer=None):
      region = self._get_region_name(layer)
      marks = self.view.get_regions(region)
      
      for mark in newMarks:
         if mark in marks:
            marks.remove(mark)
         else:
            marks.append(mark)

      self.view.add_regions(region, marks, '', '', sublime.PERSISTENT)

      if layer == self.layer:
         self._render()

   # Changes the layer to the given one and updates any and all of the status indicators.
   def _change_to_layer(self, layer):
      self.layer = layer
      status_name = 'bb_layer_status'

      status = Settings().get('layer_status_location', ['permanent'])

      if 'temporary' in status:
         sublime.status_message(self.layer)
      if 'permanent' in status:
         self.view.set_status(status_name, 'Bookmark Layer: {:s}'.format(self.layer))
      else:
         self.view.erase_status(status_name)
      if 'popup' in status:
         if self.view.is_popup_visible():
            self.view.update_popup(self.layer)
         else:
            self.view.show_popup(self.layer, 0, -1, 1000, 1000, None, None)

      self._render()

   # An empty view only overwrites the cache once this view has loaded it, so a
   #  view whose marks were never restored can't wipe the synced cache.
   def _save_marks(self):
      if not self.view.file_name():
         return
      if self._is_empty() and self.view.id() not in Loaded:
         return
      Log('Saving BBFile for ' + self.filename)
      marks = {'filename': self.view.file_name(), 'bookmarks': {}}
      for layer in self.layers:
         marks['bookmarks'][layer] = [ToMark(self.view, mark) for mark in self.view.get_regions(self._get_region_name(layer))]
      with open(self._get_cache_filename(), 'w') as fp:
         json.dump(marks, fp)

   # Write as soon as marks change, so syncs and reloads see current marks.
   def _save_marks_now(self):
      if Settings().get('cache_marks_on_save'):
         self._save_marks()

   def _load_marks(self):
      Log('Loading BBFile for ' + self.filename)
      for layer in self.layers:
         self.view.erase_regions(self._get_region_name(layer))
      try:
         with open(self._get_cache_filename(), 'r') as fp:
            data = json.load(fp)
      except (OSError, ValueError):
         data = {'bookmarks': {}}
      lines = self.view.substr(sublime.Region(0, self.view.size())).split('\n')
      for name, marks in data['bookmarks'].items():
         self._add_marks([FromMark(self.view, lines, mark) for mark in marks], name)
      Loaded.add(self.view.id())

   def run(self, edit, **args):
      view = self.view
      subcommand = args['subcommand']

      if subcommand == 'mark_line':
         mode = Settings().get('marking_mode', 'selection')

         if mode == 'line':
            selection = view.lines(view.sel()[0])
         elif mode == 'selection':
            selection = view.sel()
         else:
            sublime.error_message('Invalid BetterBookmarks setting: \'{}\' is invalid for \'marking_mode\''.format(mode))

         line = args['line'] if 'line' in args else selection
         layer = args['layer'] if 'layer' in args else self.layer

         self._add_marks(line, layer)
         self._save_marks_now()
      elif subcommand == 'cycle_mark':
         self.view.run_command('{}_bookmark'.format(args['direction']), {'name': 'better_bookmarks'})
      elif subcommand == 'clear_marks':
         layer = args['layer'] if 'layer' in args else self.layer
         self.view.erase_regions('better_bookmarks')
         self.view.erase_regions(self._get_region_name(layer))
         self._save_marks_now()
      elif subcommand == 'clear_all':
         self.view.erase_regions('better_bookmarks')
         for layer in self.layers:
            self.view.erase_regions(self._get_region_name(layer))
         self._save_marks_now()
      elif subcommand == 'layer_swap':
         direction = args.get('direction')
         if direction == 'prev':
            self.layers.rotate(-1)
         elif direction == 'next':
            self.layers.rotate(1)
         else:
            sublime.error_message('Invalid layer swap direction.')

         self._change_to_layer(self.layers[0])
      elif subcommand == 'on_load':
         self._load_marks()
         self._change_to_layer(Settings().get('default_layer'))
      elif subcommand == 'on_save':
         self._save_marks()
      elif subcommand == 'on_close':
         if Settings().get('cache_marks_on_close', False):
            self._save_marks()
         # Only a view that loaded its marks can know the cache should be empty.
         if Settings().get('cleanup_empty_cache_on_close', False) and self._is_empty() and self.view.id() in Loaded:
            Log('Removing BBFile for ' + self.filename)
            try:
               os.remove(self._get_cache_filename())
            except OSError:
               pass
         Loaded.discard(self.view.id())

class BetterBookmarksEventListener(sublime_plugin.EventListener):
   def __init__(self):
      sublime_plugin.EventListener.__init__(self)

   def _contact(self, view, subcommand):
      view.run_command('better_bookmarks', {'subcommand': subcommand})

   def on_load_async(self, view):
      if Settings().get('uncache_marks_on_load'):
         self._contact(view, 'on_load')

   # The file changed on disk, so re-anchor from the cache, which is only
   #  current if marks are written as they change.
   def on_reload_async(self, view):
      if view.file_name() and Settings().get('uncache_marks_on_load') and Settings().get('cache_marks_on_save'):
         self._contact(view, 'on_load')

   # Views restored from a session may never get on_load.
   def on_activated_async(self, view):
      if view.file_name() and not view.is_loading() and view.id() not in Loaded and Settings().get('uncache_marks_on_load'):
         self._contact(view, 'on_load')

   def on_pre_save(self, view):
      if Settings().get('cache_marks_on_save'):
         self._contact(view, 'on_save')

   def on_close(self, view):
      if view.file_name():
         self._contact(view, 'on_close')
