class ApplicationController < ActionController::Base
  def index
    render html: "<h1>Welcome to StatMon</h1><p>You're up and running!</p>".html_safe
  end
end
