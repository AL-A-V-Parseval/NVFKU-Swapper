#include "my_application.h"

#include <string.h>

#include <flutter_linux/flutter_linux.h>
#ifdef GDK_WINDOWING_X11
#include <gdk/gdkx.h>
#endif

#include "flutter/generated_plugin_registrant.h"

struct _MyApplication {
  GtkApplication parent_instance;
  char** dart_entrypoint_arguments;
};

G_DEFINE_TYPE(MyApplication, my_application, GTK_TYPE_APPLICATION)

// Called when first Flutter frame received.
static void first_frame_cb(MyApplication* self, FlView* view) {
  gtk_widget_show(gtk_widget_get_toplevel(GTK_WIDGET(view)));
}


// The two colours Flutter paints its own background with — the `surface` slot of the
// two `ColorScheme`s in `app/lib/src/app.dart`. Duplicated here because the header bar
// is drawn by GTK, before and outside Flutter's raster, so Dart cannot tell GTK what
// it used.
//
// Both were measured off a running window rather than read out of the source. The
// first light value here was guessed from the wrong slot (`#F7F9FA`) and was visibly
// wrong next to the real body (`#EEF1F4`).
#define NVFKU_DARK_BG "#09090A"
#define NVFKU_LIGHT_BG "#EEF1F4"

//: Where the engine keeps its settings, relative to the state directory.
#define NVFKU_SETTINGS_FILE "settings.json"

// The directory holding settings, journals and caches.
//
// Mirrors `Paths.discover` in the engine: the override first, then `XDG_DATA_HOME`,
// then `~/.local/share`. It has to match, because the value read from here decides the
// header colour and a mismatch would paint the bar for the other theme.
static gchar* nvfku_state_dir(void) {
  const gchar* override = g_getenv("NVFKU_STATE_DIR");
  if (override != nullptr && *override != '\0') {
    return g_strdup(override);
  }
  const gchar* data_home = g_getenv("XDG_DATA_HOME");
  if (data_home != nullptr && *data_home != '\0') {
    return g_build_filename(data_home, "nvfku", nullptr);
  }
  return g_build_filename(g_get_home_dir(), ".local", "share", "nvfku", nullptr);
}

static gchar* nvfku_settings_path(void) {
  g_autofree gchar* state = nvfku_state_dir();
  return g_build_filename(state, NVFKU_SETTINGS_FILE, nullptr);
}

// The stored theme, or null when it is absent or unreadable.
//
// A hand-rolled scan rather than a JSON parser: the file holds one flat object of
// strings, booleans, numbers and one nested object, and pulling in a dependency for
// this would be worse than the twenty lines. Only `"theme"` is looked for, at the top
// level, and an unparseable file yields null so the caller falls back to the desktop.
static gchar* nvfku_stored_theme(void) {
  g_autofree gchar* path = nvfku_settings_path();
  g_autofree gchar* contents = nullptr;
  if (!g_file_get_contents(path, &contents, nullptr, nullptr)) {
    return nullptr;
  }
  const gchar* key = "\"theme\"";
  const gchar* at = strstr(contents, key);
  if (at == nullptr) {
    return nullptr;
  }
  at += strlen(key);
  while (*at == ' ' || *at == '\t' || *at == ':' || *at == '\n' || *at == '\r') {
    at++;
  }
  if (*at != '"') {
    return nullptr;
  }
  at++;
  const gchar* end = strchr(at, '"');
  if (end == nullptr) {
    return nullptr;
  }
  return g_strndup(at, (gsize)(end - at));
}

// Whether the desktop prefers a dark interface.
//
// `color-scheme` is the key the Linux embedder consults for platform brightness; the
// theme *name* is the fallback for desktops that never set it, which is what GTK apps
// did before the key existed.
static gboolean nvfku_desktop_prefers_dark(void) {
  GSettingsSchemaSource* source = g_settings_schema_source_get_default();
  if (source != nullptr) {
    g_autoptr(GSettingsSchema) schema =
        g_settings_schema_source_lookup(source, "org.gnome.desktop.interface", TRUE);
    if (schema != nullptr && g_settings_schema_has_key(schema, "color-scheme")) {
      g_autoptr(GSettings) settings = g_settings_new("org.gnome.desktop.interface");
      g_autofree gchar* scheme = g_settings_get_string(settings, "color-scheme");
      if (g_strcmp0(scheme, "prefer-dark") == 0) {
        return TRUE;
      }
      if (g_strcmp0(scheme, "prefer-light") == 0 || g_strcmp0(scheme, "default") == 0) {
        return FALSE;
      }
    }
  }
  g_autoptr(GtkSettings) gtk_settings = gtk_settings_get_default();
  if (gtk_settings == nullptr) {
    return FALSE;
  }
  g_autofree gchar* theme_name = nullptr;
  g_object_get(gtk_settings, "gtk-theme-name", &theme_name, nullptr);
  if (theme_name == nullptr) {
    return FALSE;
  }
  g_autofree gchar* lowered = g_ascii_strdown(theme_name, -1);
  return strstr(lowered, "dark") != nullptr;
}

// Paint the header bar as part of the app rather than as a band of the desktop theme.
//
// The seam this removes was measured: GTK resolved the header bar to #2C2C2C while
// the app painted #09090A underneath it, which read as a strip belonging to something
// else sitting on top of the window.
//
// `background-image: none` is required, not cosmetic. The default header bar paints
// a gradient and its shadow through `background-image`, so setting only
// `background-color` leaves both in place.
//
// `gtk_style_context_add_provider` is given a context the widget owns, and it takes
// its own reference on the provider, so neither needs freeing here. Taking a
// reference on the context to manage it would corrupt GTK's bookkeeping — that
// mistake crashed the process with a SIGBUS inside `g_type_create_instance` before
// the window was ever mapped.
// The colour the header bar should take.
//
// The app's own setting comes first, and only when it is absent or set to `system`
// does the desktop decide. Reading the desktop *alone* — which this did first — is
// wrong as soon as the app can override it: with the stored theme set to `light` on a
// `prefer-dark` desktop, the bar kept the dark colour and sat above a light window.
// That is the opposite of the seam this exists to remove, and it was caught by
// measuring, not by looking.
static gboolean nvfku_uses_dark(void) {
  g_autofree gchar* stored = nvfku_stored_theme();
  if (stored != nullptr) {
    if (g_strcmp0(stored, "dark") == 0) {
      return TRUE;
    }
    if (g_strcmp0(stored, "light") == 0) {
      return FALSE;
    }
  }
  return nvfku_desktop_prefers_dark();
}

static void nvfku_apply_headerbar_theme(GtkWidget* header_bar) {
  const gchar* background = nvfku_uses_dark() ? NVFKU_DARK_BG : NVFKU_LIGHT_BG;
  g_autofree gchar* css = g_strdup_printf(
      "#nvfku-headerbar {"
      "  background-image: none;"
      "  background-color: %s;"
      "  border: none;"
      "  box-shadow: none;"
      "  border-radius: 0;"
      "}"
      // The controls keep their size and position; only the surrounding gap shrinks
      // slightly, since the bar no longer needs room for a theme-drawn separator.
      "#nvfku-headerbar > windowcontrols { margin: 4px; }",
      background);

  GtkCssProvider* provider = gtk_css_provider_new();
  gtk_css_provider_load_from_data(provider, css, -1, nullptr);
  gtk_style_context_add_provider(gtk_widget_get_style_context(header_bar),
                                 GTK_STYLE_PROVIDER(provider),
                                 GTK_STYLE_PROVIDER_PRIORITY_USER);
  g_object_unref(provider);
}

// Repaint when the desktop switches between light and dark while the app is running,
// so a live toggle does not leave the bar on the old colour. When the user has chosen
// a theme explicitly this is harmless: `nvfku_uses_dark` ignores the desktop.
static void nvfku_color_scheme_changed(GSettings* settings, gchar* key,
                                       gpointer user_data) {
  nvfku_apply_headerbar_theme(GTK_WIDGET(user_data));
}

// Repaint when the settings file changes.
//
// This is what makes the in-app picker take effect immediately. Flutter repaints
// itself the moment the notifier changes, but the header bar belongs to GTK and has no
// way to hear about it — without this the bar keeps the old colour until the next
// launch, which is a one-frame-wide version of the seam problem.
static void nvfku_settings_changed(GFileMonitor* monitor, GFile* file, GFile* other,
                                   GFileMonitorEvent event, gpointer user_data) {
  if (event == G_FILE_MONITOR_EVENT_CHANGED ||
      event == G_FILE_MONITOR_EVENT_CREATED ||
      event == G_FILE_MONITOR_EVENT_CHANGES_DONE_HINT) {
    nvfku_apply_headerbar_theme(GTK_WIDGET(user_data));
  }
}

// Implements GApplication::activate.
static void my_application_activate(GApplication* application) {
  MyApplication* self = MY_APPLICATION(application);
  GtkWindow* window =
      GTK_WINDOW(gtk_application_window_new(GTK_APPLICATION(application)));

  // Use a header bar when running in GNOME as this is the common style used
  // by applications and is the setup most users will be using (e.g. Ubuntu
  // desktop).
  // If running on X and not using GNOME then just use a traditional title bar
  // in case the window manager does more exotic layout, e.g. tiling.
  // If running on Wayland assume the header bar will work (may need changing
  // if future cases occur).
  gboolean use_header_bar = TRUE;
#ifdef GDK_WINDOWING_X11
  GdkScreen* screen = gtk_window_get_screen(window);
  if (GDK_IS_X11_SCREEN(screen)) {
    const gchar* wm_name = gdk_x11_screen_get_window_manager_name(screen);
    if (g_strcmp0(wm_name, "GNOME Shell") != 0) {
      use_header_bar = FALSE;
    }
  }
#endif
  if (use_header_bar) {
    GtkHeaderBar* header_bar = GTK_HEADER_BAR(gtk_header_bar_new());
    gtk_widget_show(GTK_WIDGET(header_bar));
    // Named so the stylesheet targets this bar and nothing else.
    gtk_widget_set_name(GTK_WIDGET(header_bar), "nvfku-headerbar");
    // No title text: the sidebar already carries the name in a larger size, and two
    // of them made the window look labelled twice. The window title below still
    // supplies "NVFKU-Swapper" to the taskbar and window list, so nothing loses it.
    gtk_header_bar_set_title(header_bar, "");
    gtk_header_bar_set_show_close_button(header_bar, TRUE);
    nvfku_apply_headerbar_theme(GTK_WIDGET(header_bar));
    gtk_window_set_titlebar(window, GTK_WIDGET(header_bar));

    GSettingsSchemaSource* source = g_settings_schema_source_get_default();
    if (source != nullptr) {
      g_autoptr(GSettingsSchema) schema = g_settings_schema_source_lookup(
          source, "org.gnome.desktop.interface", TRUE);
      if (schema != nullptr && g_settings_schema_has_key(schema, "color-scheme")) {
        GSettings* settings = g_settings_new("org.gnome.desktop.interface");
        g_signal_connect_object(settings, "changed::color-scheme",
                                G_CALLBACK(nvfku_color_scheme_changed),
                                header_bar, G_CONNECT_DEFAULT);
        g_object_unref(settings);
      }
    }

    // Watch the settings file so a change made in the app repaints the bar. The monitor
    // is owned by the window: without an owner it would be collected and the callback
    // would stop arriving.
    g_autofree gchar* settings_path = nvfku_settings_path();
    g_autoptr(GFile) settings_file = g_file_new_for_path(settings_path);
    GFileMonitor* monitor = g_file_monitor_file(settings_file, G_FILE_MONITOR_NONE,
                                                nullptr, nullptr);
    if (monitor != nullptr) {
      g_signal_connect_object(monitor, "changed",
                              G_CALLBACK(nvfku_settings_changed), header_bar,
                              G_CONNECT_DEFAULT);
      g_object_ref_sink(monitor);
    }
  }
  // Set unconditionally: the header bar's own title is empty, and this is what the
  // compositor, taskbar and window list read.
  gtk_window_set_title(window, "NVFKU-Swapper");

  gtk_window_set_default_size(window, 1280, 720);

  g_autoptr(FlDartProject) project = fl_dart_project_new();
  fl_dart_project_set_dart_entrypoint_arguments(
      project, self->dart_entrypoint_arguments);

  FlView* view = fl_view_new(project);
  GdkRGBA background_color;
  // Background defaults to black, override it here if necessary, e.g. #00000000
  // for transparent.
  gdk_rgba_parse(&background_color, "#000000");
  fl_view_set_background_color(view, &background_color);
  gtk_widget_show(GTK_WIDGET(view));
  gtk_container_add(GTK_CONTAINER(window), GTK_WIDGET(view));

  // Show the window when Flutter renders.
  // Requires the view to be realized so we can start rendering.
  g_signal_connect_swapped(view, "first-frame", G_CALLBACK(first_frame_cb),
                           self);
  gtk_widget_realize(GTK_WIDGET(view));

  fl_register_plugins(FL_PLUGIN_REGISTRY(view));

  gtk_widget_grab_focus(GTK_WIDGET(view));
}

// Implements GApplication::local_command_line.
static gboolean my_application_local_command_line(GApplication* application,
                                                  gchar*** arguments,
                                                  int* exit_status) {
  MyApplication* self = MY_APPLICATION(application);
  // Strip out the first argument as it is the binary name.
  self->dart_entrypoint_arguments = g_strdupv(*arguments + 1);

  g_autoptr(GError) error = nullptr;
  if (!g_application_register(application, nullptr, &error)) {
    g_warning("Failed to register: %s", error->message);
    *exit_status = 1;
    return TRUE;
  }

  g_application_activate(application);
  *exit_status = 0;

  return TRUE;
}

// Implements GApplication::startup.
static void my_application_startup(GApplication* application) {
  // MyApplication* self = MY_APPLICATION(object);

  // Perform any actions required at application startup.

  G_APPLICATION_CLASS(my_application_parent_class)->startup(application);
}

// Implements GApplication::shutdown.
static void my_application_shutdown(GApplication* application) {
  // MyApplication* self = MY_APPLICATION(object);

  // Perform any actions required at application shutdown.

  G_APPLICATION_CLASS(my_application_parent_class)->shutdown(application);
}

// Implements GObject::dispose.
static void my_application_dispose(GObject* object) {
  MyApplication* self = MY_APPLICATION(object);
  g_clear_pointer(&self->dart_entrypoint_arguments, g_strfreev);
  G_OBJECT_CLASS(my_application_parent_class)->dispose(object);
}

static void my_application_class_init(MyApplicationClass* klass) {
  G_APPLICATION_CLASS(klass)->activate = my_application_activate;
  G_APPLICATION_CLASS(klass)->local_command_line =
      my_application_local_command_line;
  G_APPLICATION_CLASS(klass)->startup = my_application_startup;
  G_APPLICATION_CLASS(klass)->shutdown = my_application_shutdown;
  G_OBJECT_CLASS(klass)->dispose = my_application_dispose;
}

static void my_application_init(MyApplication* self) {}

MyApplication* my_application_new() {
  // Set the program name to the application ID, which helps various systems
  // like GTK and desktop environments map this running application to its
  // corresponding .desktop file. This ensures better integration by allowing
  // the application to be recognized beyond its binary name.
  g_set_prgname(APPLICATION_ID);

  return MY_APPLICATION(g_object_new(my_application_get_type(),
                                     "application-id", APPLICATION_ID, "flags",
                                     G_APPLICATION_NON_UNIQUE, nullptr));
}
