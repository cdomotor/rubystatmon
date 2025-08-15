# File: app/models/reading.rb
# Path: C:/rubystatmon-fetched/rubystatmon/app/models/reading.rb

class Reading < ApplicationRecord
  belongs_to :station
  validates :parameter, presence: true
  validates :taken_at, presence: true
end
