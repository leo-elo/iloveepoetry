module Jekyll
  class CategoryPage < Page
    def initialize(site, base, dir, category_name, category_slug, lang)
      @site = site
      @base = base
      @dir = dir
      @name = "#{category_slug}.html"

      self.process(@name)

      # Don't use read_yaml - set data directly to avoid shared Liquid state
      self.data = {
        'layout' => 'category',
        'title' => category_name,
        'category_name' => category_name,
        'category_slug' => category_slug,
        'lang' => lang,
      }
      self.content = ''
    end
  end

  class CategoryPageGenerator < Generator
    safe true
    priority :low

    def generate(site)
      # Collect all unique categories across all posts
      categories = {}

      skip_categories = ['uncategorized', 'sin-categorizar']

      site.posts.docs.each do |post|
        post.data['categories'].each do |cat|
          cat_str = cat.to_s
          slug = Utils.slugify(cat_str)
          next if skip_categories.include?(slug)
          categories[slug] ||= { name: cat_str, slug: slug }
        end
      end

      # For each category, generate EN and ES pages
      categories.each_value do |cat_info|
        ['en', 'es'].each do |lang|
          dir = File.join(lang, 'category')
          site.pages << CategoryPage.new(
            site,
            site.source,
            dir,
            cat_info[:name],
            cat_info[:slug],
            lang
          )
        end
      end
    end
  end
end
