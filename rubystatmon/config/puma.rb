max_threads_count = ENV.fetch('RAILS_MAX_THREADS', 5)
port ENV.fetch('PORT', 3000)
plugin :tmp_restart
