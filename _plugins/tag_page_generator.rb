module Jekyll
  class TagPage < Page
    def initialize(site, base, dir, tag_name, tag_slug, lang)
      @site = site
      @base = base
      @dir = dir
      @name = "#{tag_slug}.html"

      self.process(@name)

      self.data = {
        'layout' => 'tag',
        'title' => tag_name,
        'tag_name' => tag_name,
        'tag_slug' => tag_slug,
        'lang' => lang,
      }
      self.content = ''
    end
  end

  class TagPageGenerator < Generator
    safe true
    priority :low

    def generate(site)
      tags = {}

      site.posts.docs.each do |post|
        next unless post.data['tags']
        post.data['tags'].each do |tag|
          tag_str = tag.to_s.strip
          next if tag_str.empty?
          slug = Utils.slugify(tag_str)
          next if slug.nil? || slug.empty?
          tags[slug] ||= { name: tag_str, slug: slug }
        end
      end

      tags.each_value do |tag_info|
        ['en', 'es'].each do |lang|
          dir = File.join(lang, 'tag')
          site.pages << TagPage.new(
            site,
            site.source,
            dir,
            tag_info[:name],
            tag_info[:slug],
            lang
          )
        end
      end
    end
  end
end
