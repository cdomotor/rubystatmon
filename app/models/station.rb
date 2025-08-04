class Station < ApplicationRecord
    has_many :ping_result, dependent: :destroy
end
